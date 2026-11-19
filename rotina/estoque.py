#!/usr/bin/env python3
"""SIMULAÇÃO (só leitura): calcula o que a rotina movimentaria no estoque e quais APs poderia finalizar.
Não escreve nada no Farmbox.

Uso: python estoque.py <pasta_paginas_aps> <pasta_paginas_movimentacoes> <relatorio.json> [relatorio.md]

Regras (definidas pela Daniela, 18/11/2026):
- Os operadores lançam a área aplicada direto no Farmbox. A rotina só movimenta o estoque:
  saída = área aplicada x dose da receita, por insumo, só a DIFERENÇA ainda não movimentada na AP.
- Finalizar a AP somente se (área aplicada >= 99,5% da solicitada OU algum lançamento tem "FINAL" nos comentários)
  E nenhum produto da AP ficar com saldo negativo ou não verificável. Caso contrário a AP fica aberta.
- Aplicada menor que a solicitada, sem "FINAL": vai para a lista "possível conclusão" (decisão humana).
- Saldo negativo ou não verificável SEMPRE bloqueia a finalização (nunca ajustar estoque para "limpar" o negativo).
"""
import sys, os, re, json, glob, io, collections, datetime as dt

TOL_AREA = 0.995            # 99,5% da área solicitada conta como concluída
TOL_QTD = 0.0005            # abaixo disso, considera zero
DEPOSITOS = {15254: 'INSUMOS - BOM JESUS', 25684: 'INSUMOS - STO ANTO I'}   # nunca o 15224 (Sucupira)
UNID_DOSE = {'l_ha': 'l', 'kg_ha': 'kg'}                                      # unidade da quantidade para cada unidade de dose
RE_FINAL = re.compile(r'\bFINAL\b')                                           # exatamente em maiúsculas


def carrega(f):
    t = io.open(f, encoding='utf-8').read()
    if t.lstrip().startswith('['):
        t = json.loads(t)[0]['text']
    return json.loads(t[t.index('{'):])


def le_pasta(pasta, chave):
    out = []
    for f in sorted(glob.glob(os.path.join(pasta, '*'))):
        try:
            out += carrega(f)[chave]
        except (KeyError, ValueError):
            continue
    return out


def saldos(movs):
    """(input_id, depósito, unidade) -> saldo (entradas - saídas). Tipos desconhecidos tornam o insumo NÃO VERIFICADO."""
    s = collections.defaultdict(float)
    desconhecido = set()
    for m in movs:
        k = (m['input_id'], m['storage_id'], m['unit'])
        t = m.get('movimentation_type')
        if t == 'in':
            s[k] += m['quantity']
        elif t == 'out':
            s[k] -= m['quantity']
        else:
            desconhecido.add(m['input_id'])
    return s, desconhecido


def fmt(v, c=2):
    return f'{v:,.{c}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def analisa(aps, movs):
    S, desconhecido = saldos(movs)
    unidades = collections.defaultdict(set)                  # input_id -> unidades vistas no estoque
    for (iid, dep, un) in S:
        unidades[iid].add(un)
    resultado = []
    for a in aps:
        if a.get('status') == 'finalized':
            continue
        sol = sum(p.get('sought_area') or 0 for p in a['plantations'])
        apl = sum(p.get('applied_area') or 0 for p in a['plantations'])
        apl_prog = sum(p.get('area') or 0 for p in a['progresses'])
        pct = apl / sol if sol else 0
        sinal_final = any(RE_FINAL.search(p.get('comment') or '') for p in a['progresses'])
        usados = collections.defaultdict(lambda: collections.defaultdict(float))     # input -> depósito -> já movido na AP
        for m in a['input_movimentations']:
            sinal = 1 if m['kind'] == 'removed' else -1
            usados[m['input_id']][m['storage_id']] += sinal * m['value']
        insumos, bloqueios, avisos = [], [], []
        if apl_prog and abs(apl - apl_prog) > 0.05:
            avisos.append(f'área dos talhões ({fmt(apl)} ha) difere da soma dos lançamentos ({fmt(apl_prog)} ha)')
        for i in a['inputs']:
            iid, nome = i['input']['id'], i['input']['name']
            dose, ud = i.get('sought_dosage_value'), i.get('sought_dosage_unit')
            un_esp = UNID_DOSE.get(ud)
            linha = {'insumo': nome, 'input_id': iid, 'dose': dose, 'unidade_dose': ud}
            if dose is None or un_esp is None:
                linha['situacao'] = 'NÃO VERIFICADO'; linha['motivo'] = f'unidade de dose desconhecida ({ud})'
                bloqueios.append(f'{nome}: unidade de dose desconhecida'); insumos.append(linha); continue
            esperado = apl * dose
            movido = sum(usados[iid].values())
            falta = esperado - movido
            if abs(falta) <= max(0.01, 0.001 * esperado):      # diferença de arredondamento (ex.: 0,001): considera igual
                falta = 0.0
            linha.update({'unidade': un_esp, 'esperado': round(esperado, 3), 'ja_movido': round(movido, 3), 'a_movimentar': round(falta, 3),
                          'aplicado_farmbox': i.get('applied'), 'consumido_farmbox': i.get('consumed')})
            if falta < 0:
                avisos.append(f'{nome}: já movido ({fmt(movido, 3)}) é MAIOR que o calculado ({fmt(esperado, 3)}); a rotina não corrige, só avisa')
            # depósitos (regra da Daniela, 18/11/2026): usa o que tiver saldo; se um sozinho cobre, usa ele (primeiro o já usado
            # na AP, depois BOM JESUS, depois STO ANTO I); se nenhum cobre sozinho, divide entre os dois; só bloqueia se a SOMA não cobrir
            ordem = sorted(usados[iid], key=lambda d: -usados[iid][d]) + [d for d in DEPOSITOS if d not in usados[iid]]
            linha['saldos'] = {DEPOSITOS[d]: round(S.get((iid, d, un_esp), 0), 3) for d in DEPOSITOS}
            problema = None
            if iid in desconhecido:
                problema = 'tipo de movimentação desconhecido no histórico'
            elif unidades[iid] and un_esp not in unidades[iid]:
                problema = f'unidade do estoque ({"/".join(sorted(unidades[iid]))}) diferente da AP ({un_esp})'
            elif not unidades[iid]:
                problema = 'sem histórico de estoque deste insumo'
            if problema:
                linha['situacao'] = 'NÃO VERIFICADO'; linha['motivo'] = problema
                bloqueios.append(f'{nome}: {problema}')
            else:
                restante = max(falta, 0.0)
                alocacao = {}
                unico = next((d for d in ordem if S.get((iid, d, un_esp), 0.0) >= restante), None)
                if unico is not None:
                    if restante > 0:
                        alocacao[unico] = restante
                    restante = 0.0
                else:
                    for d in ordem:
                        if restante <= TOL_QTD:
                            break
                        tira = min(restante, max(S.get((iid, d, un_esp), 0.0), 0.0))
                        if tira > 0:
                            alocacao[d] = tira
                            restante -= tira
                saldo_apos = {d: S.get((iid, d, un_esp), 0.0) - alocacao.get(d, 0.0) for d in DEPOSITOS}
                linha['saidas'] = [{'deposito': DEPOSITOS[d], 'quantidade': round(q, 3)} for d, q in alocacao.items()]
                linha['deposito'] = ' + '.join(f'{DEPOSITOS[d]} {fmt(q, 3)}' for d, q in alocacao.items()) or \
                    (' + '.join(DEPOSITOS[d] for d in usados[iid]) if usados[iid] else '-')
                linha['saldo_apos'] = {DEPOSITOS[d]: round(v, 3) for d, v in saldo_apos.items()}
                negativos = [d for d in DEPOSITOS if saldo_apos[d] < -TOL_QTD and (d in alocacao or d in usados[iid])]
                if restante > TOL_QTD:
                    linha['situacao'] = 'NEGATIVO'
                    todos = ', '.join(f'{DEPOSITOS[d]}: {fmt(S.get((iid, d, un_esp), 0.0), 3)}' for d in DEPOSITOS)
                    bloqueios.append(f'{nome}: estoque insuficiente nos dois depósitos (faltam {fmt(restante, 3)} {un_esp}; saldos {todos})')
                elif negativos:
                    linha['situacao'] = 'NEGATIVO'
                    bloqueios.append(f'{nome}: saldo negativo no {", ".join(DEPOSITOS[d] for d in negativos)} ({fmt(min(saldo_apos[d] for d in negativos), 3)} {un_esp})')
                else:
                    linha['situacao'] = 'REGULAR'
            insumos.append(linha)
        concluida = pct >= TOL_AREA or sinal_final
        if apl <= 0:
            situacao = 'SEM APLICAÇÃO'
        elif bloqueios and concluida:
            situacao = 'BLOQUEADA (estoque)'
        elif bloqueios:
            situacao = 'ABERTA (estoque com problema)'
        elif concluida:
            situacao = 'FINALIZAR'
        else:
            situacao = 'POSSÍVEL CONCLUSÃO'
        resultado.append({
            'ap': a['code'], 'id': a['id'], 'atividade': (a.get('activity_type') or {}).get('name'),
            'data': a.get('date'), 'solicitada_ha': round(sol, 2), 'aplicada_ha': round(apl, 2), 'pct': round(pct * 100, 1),
            'sinal_final': sinal_final, 'ultimo_lancamento': max((p['date'][:10] for p in a['progresses']), default=None),
            'situacao': situacao, 'bloqueios': bloqueios, 'avisos': avisos, 'insumos': insumos})
    return resultado


def previsao(aps, movs):
    """Para cada insumo das APs abertas: quanto falta aplicar (área ainda não aplicada x dose) x saldo total nos depósitos."""
    S, _ = saldos(movs)
    precisa = collections.defaultdict(float)
    nomes = {}
    for a in aps:
        if a.get('status') == 'finalized':
            continue
        sol = sum(p.get('sought_area') or 0 for p in a['plantations'])
        apl = sum(p.get('applied_area') or 0 for p in a['plantations'])
        restante = max(sol - apl, 0)
        for i in a['inputs']:
            un = UNID_DOSE.get(i.get('sought_dosage_unit'))
            if un and i.get('sought_dosage_value') is not None:
                k = (i['input']['id'], un)
                precisa[k] += restante * i['sought_dosage_value']
                nomes[k] = i['input']['name']
    linhas = []
    for (iid, un), q in precisa.items():
        total = sum(S.get((iid, d, un), 0) for d in DEPOSITOS)
        linhas.append({'insumo': nomes[(iid, un)], 'unidade': un, 'a_aplicar': round(q, 2), 'saldo_total': round(total, 2),
                       'situacao': 'FALTARÁ' if total < q else 'OK', 'diferenca': round(total - q, 2)})
    return sorted(linhas, key=lambda x: x['diferenca'])


def relatorio_md(res, agora, prev=None):
    L = [f'# Simulação da rotina de estoque, {agora}', '', '**Modo simulação: nada foi escrito no Farmbox.**', '']
    cont = collections.Counter(r['situacao'] for r in res)
    L.append('Resumo: ' + ' | '.join(f'{k}: {v}' for k, v in sorted(cont.items())))
    L += ['', '| AP | Atividade | Aplicada / Solicitada | % | Último lançamento | FINAL | Situação |', '|---|---|---|---|---|---|---|']
    for r in res:
        L.append(f"| {r['ap']} | {r['atividade']} | {fmt(r['aplicada_ha'])} / {fmt(r['solicitada_ha'])} ha | {fmt(r['pct'], 1)}% | {r['ultimo_lancamento'] or '-'} | {'sim' if r['sinal_final'] else 'não'} | {r['situacao']} |")
    for r in res:
        if r['situacao'] == 'SEM APLICAÇÃO':
            continue
        L += ['', f"## {r['ap']} ({r['atividade']}): {r['situacao']}"]
        for b in r['bloqueios']:
            L.append(f'- BLOQUEIO: {b}')
        for v in r['avisos']:
            L.append(f'- Aviso: {v}')
        L += ['', '| Insumo | Dose | Esperado | Já movido | A movimentar | Depósito | Saldo depois | Situação |', '|---|---|---|---|---|---|---|---|']
        for i in r['insumos']:
            if 'esperado' not in i:
                L.append(f"| {i['insumo']} | - | - | - | - | - | - | {i['situacao']}: {i.get('motivo', '')} |")
                continue
            saldo_txt = ' / '.join(f"{k.replace('INSUMOS - ', '')}: {fmt(v, 3)}" for k, v in i['saldo_apos'].items()) if 'saldo_apos' in i else '-'
            L.append(f"| {i['insumo']} | {i['dose']} {i['unidade_dose']} | {fmt(i['esperado'], 3)} {i['unidade']} | {fmt(i['ja_movido'], 3)} | {fmt(i['a_movimentar'], 3)} {i['unidade']} | {i['deposito']} | {saldo_txt} | {i['situacao']} |")
    if prev:
        L += ['', '## Previsão: o estoque cobre o que ainda falta aplicar nas APs abertas?', '',
              '| Insumo | A aplicar | Saldo total (2 depósitos) | Diferença | Situação |', '|---|---|---|---|---|']
        for p in prev:
            L.append(f"| {p['insumo']} | {fmt(p['a_aplicar'])} {p['unidade']} | {fmt(p['saldo_total'])} {p['unidade']} | {fmt(p['diferenca'])} | {p['situacao']} |")
    return '\n'.join(L) + '\n'


if __name__ == '__main__':
    pasta_aps, pasta_movs, saida = sys.argv[1:4]
    aps = le_pasta(pasta_aps, 'applications')
    movs = le_pasta(pasta_movs, 'movimentations')
    if not movs:
        sys.exit('Sem movimentações de estoque: simulação não executada (sem histórico não há como calcular saldo).')
    res = analisa(aps, movs)
    prev = previsao(aps, movs)
    agora = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=-3)).strftime('%d/%m/%Y %H:%M')
    json.dump({'gerado': agora, 'simulacao': True, 'aps': res, 'previsao': prev}, open(saida, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    md = relatorio_md(res, agora, prev)
    if len(sys.argv) > 4:
        open(sys.argv[4], 'w', encoding='utf-8').write(md)
    print(f'{len(aps)} APs lidas, {len(movs)} movimentações; {len(res)} APs abertas analisadas')
    print('situações:', dict(collections.Counter(r['situacao'] for r in res)))
    if os.environ.get('GITHUB_ACTIONS') == 'true':      # resumo curto como anotação da execução (sem saldos)
        cont = collections.Counter(r['situacao'] for r in res)
        print('::notice title=Estoque (simulação)::' + ' | '.join(f'{k}: {v}' for k, v in sorted(cont.items())))
        for r in [x for x in res if x['situacao'] != 'SEM APLICAÇÃO'][:8]:
            extra = ('; ' + ' / '.join(r['bloqueios'])) if r['bloqueios'] else ''
            mov = ', '.join(f"{i['insumo']} {fmt(i['a_movimentar'], 3)} {i.get('unidade', '')}" for i in r['insumos'] if i.get('a_movimentar'))
            print(f"::notice title={r['ap']}::{r['situacao']} ({fmt(r['pct'], 1)}% aplicada){extra}" + (f'; a movimentar: {mov}' if mov else ''))
        faltarao = [p for p in prev if p['situacao'] == 'FALTARÁ']
        if faltarao:
            print('::warning title=Previsão de estoque::' + '; '.join(f"{p['insumo']} (faltam {fmt(-p['diferenca'])} {p['unidade']})" for p in faltarao[:8]))
