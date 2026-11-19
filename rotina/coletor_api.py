#!/usr/bin/env python3
"""Monta o coleta_farmbox.json do painel de defensivos a partir do CONECTOR (API oficial) do Farmbox,
no mesmo formato que o coletor.js gerava pelo Chrome — assim montar.py, montar_calculadora.py e
exportar_excel.py continuam iguais.

Uso: python3 coletor_api.py <pasta_com_paginas_de_aplicacoes> <plantations.txt> <saida.json>
  - pasta: um arquivo .txt/.json por página de list_applications (fazenda Bom Jesus 14106, safra 6293,
    status sought e finalized, view completa);
  - plantations.txt: list_plantations (farm_id 14106, from_harvest_ids 6293, page_size 100).
"""
import json, sys, glob, math, os, datetime as dt, collections, statistics

PASTA, PLANT, OUT = sys.argv[1:4]
TZ = dt.timezone(dt.timedelta(hours=-3))
DIAS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
UNID = {'l_ha': ('L', 'L/Ha'), 'kg_ha': ('Kg', 'Kg/Ha')}


def carrega(f):
    t = open(f, encoding='utf-8').read()
    if t.lstrip().startswith('['):          # resultado salvo como [{"type":"text","text":"..."}]
        t = json.loads(t)[0]['text']
    return json.loads(t[t.index('{'):])


from decimal import Decimal, ROUND_HALF_UP
def M(*xs):              # produto exato em decimal (evita 8,334999 -> 8,33)
    r = Decimal(1)
    for x in xs: r *= Decimal(str(x))
    return r

def br(v, casas=2):
    v = (v if isinstance(v, Decimal) else Decimal(repr(float(v)))).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
    s = f'{v:,.{casas}f}'
    return s.replace(',', '#').replace('.', ',').replace('#', '.')


def dbr(iso):            # '2026-11-04T11:28:18.000-03:00' -> '04/11/2026'
    return f'{iso[8:10]}/{iso[5:7]}/{iso[0:4]}' if iso else ''


def carimbo(iso):        # -> 'Qua, 04/11/26 - 11:28h'
    if not iso: return ''
    d = dt.datetime.fromisoformat(iso).astimezone(TZ)
    return f"{DIAS[d.weekday()]}, {d:%d/%m/%y} - {d:%H:%M}h"


P = carrega(PLANT)['plantations']
AREA = {p['id']: p['area'] for p in P}
NOME = lambda s: ' '.join((s or '').upper().split())

apps = {}
for f in sorted(glob.glob(os.path.join(PASTA, '*'))):
    for a in carrega(f)['applications']:
        apps[a['code']] = a

# De-para do tipo de atividade (só no painel; o Farmbox continua como está):
# as APs de sulco de plantio estão no Farmbox como "Biológico + Inoculante" e aqui aparecem como "Sulco de Plantio".
SULCO_APS = {'AP169', 'AP170', 'AP171', 'AP172', 'AP173', 'AP174', 'AP175'}
def ativ_depara(a):
    nome = (a.get('activity_type') or {}).get('name') or ''
    obs = (a.get('observations') or '').strip().strip('"').lower()
    if a.get('code') in SULCO_APS or obs.startswith('sulco de plantio'):
        return 'Sulco de Plantio'
    return nome


aps, pp, csv = {}, {}, []
for code, a in apps.items():
    nomes = {p['plantation']['id']: NOME(p['plantation']['name']) for p in a['plantations']}
    fin = a['status'] == 'finalized'
    ins = sorted(a.get('inputs') or [], key=lambda i: i.get('position') or 0)
    o = {'id': a['id'], 'code': code, 'status': a['status'], 'date': a['date'], 'end_date': a['end_date'],
         'closed': a['closed_date'], 'ativ': ativ_depara(a),
         'tal': [{'t': NOME(p['plantation']['name']), 'area': AREA.get(p['plantation']['id'], p['plantation']['area']), 'sol': p['sought_area'],
                  'apl': p['applied_area'], 'cult': p['plantation'].get('culture_name') or ''} for p in a['plantations']],
         'ins': [{'n': i['input']['name'], 'tipo': i['input'].get('input_type_name') or '',
                  'dose': None if fin else i.get('sought_dosage_value'), 'un': i.get('sought_dosage_unit'),
                  'q': i.get('sought_quantity')} for i in ins]}
    if not fin:
        o['prog'] = [{'t': nomes.get(x['plantation_id'], ''), 'd': (p.get('date') or '')[:10], 'ha': x['area'],
                      'eq': (p.get('equipment') or {}).get('name') or ''}
                     for p in a.get('progresses') or [] for x in p.get('plantations') or [] if x.get('area')]
    aps[code] = o

    # "PDF" da AP (página de impressão): equipamento, bico, vazão, cargas de tanque e produto por tanque
    eqs = a.get('equipments') or []
    progs = a.get('progresses') or []
    if not eqs:   # APs antigas sem equipamento: o Farmbox imprime só a área do 1º apontamento e o total de cada insumo
        x0 = round(sum(x.get('area') or 0 for p in progs for x in p.get('plantations') or []), 2) or sum(p['sought_area'] or 0 for p in a['plantations'])
        T = [f'{br(x0)} ha', 'Insumo']
        for i in ins:
            u = UNID.get(i.get('sought_dosage_unit'), ('', ''))[0]
            T += [i['input']['name'], i['input'].get('input_type_name') or '', '-', f"{br(M(i.get('sought_dosage_value') or 0, x0))} {u}"]
        T += ['Calda total', '-']
        pp[code] = '|'.join(T)
        if fin:
            for o_i, i in zip(o['ins'], ins): o_i['q'] = round((i.get('sought_dosage_value') or 0) * x0, 2)
    else:
        e = eqs[0]
        area = e.get('area') or sum(p['sought_area'] or 0 for p in a['plantations'])
        vaz, tq = e.get('solution'), e.get('tank_volume') or (e.get('equipment') or {}).get('tank_volume')
        T = [f'Equipamento 1 de {len(eqs)}', f'Área Solicitada: {br(area)} ha', (e.get('equipment') or {}).get('name') or 'Não informado']
        if e.get('beak'): T.append(e['beak']['name'])
        cargas = []
        if vaz and tq:
            uv = 'Kg' if a.get('operation_type') == 'soil_management' else 'L'   # adubação/corretivo: vazão em Kg/Ha
            T.append(f'Vazão: {br(vaz, 0) if float(vaz).is_integer() else br(vaz, 5).rstrip("0").rstrip(",")} {uv}/Ha')
            calda = area * vaz
            n = int(math.floor(calda / tq + 1e-9)); resto = calda - n * tq
            if n and resto < 0.01 * tq:          # sobra pequena: o Farmbox divide a área por igual entre os tanques
                cargas = [(n, area / n, tq)]
            else:
                if n: cargas.append((n, tq / vaz, tq))
                if resto > 1e-6: cargas.append((1, resto / vaz, resto))
            for k, h, l in cargas: T += [f'{k}x', f'{br(h)} ha', f'{br(l)} {uv}']
        T.append('Insumo')
        for i in ins:
            u = UNID.get(i.get('sought_dosage_unit'), (i.get('sought_quantity_unit') or '', ''))[0]
            dose = i.get('sought_dosage_value') or 0
            T += [i['input']['name'], i['input'].get('input_type_name') or '']
            for k, h, l in cargas: T += [f'{k}x', f'{br(dose * h, 3)} {u}']
            T.append(f'{br(M(dose, area) if dose else (i.get("sought_quantity") or 0))} {u}')
        if cargas:
            T.append('Calda total' if uv == 'L' else 'Total')
            for k, h, l in cargas: T += [f'{k}x', f'{br(l)} {uv}']
        if fin:
            for o_i, i in zip(o['ins'], ins): o_i['q'] = round((i.get('sought_dosage_value') or 0) * area, 2)
    pp[code] = '|'.join(T)

    # histórico (equivale ao CSV do botão EXPORTAR): só APs finalizadas, um registro por apontamento x talhão x insumo
    if not fin: continue
    bico = {x['equipment']['id']: (x.get('beak') or {}).get('name') or '' for x in eqs if x.get('equipment')}
    bico0 = next((v for v in bico.values() if v), 'Bico Leque')
    datas = sorted(p['date'] for p in progs if p.get('date'))
    ini, fim = (dbr(datas[0]), dbr(datas[-1])) if datas else ('', '')
    for p in reversed(progs):           # o export do Farmbox lista os apontamentos do mais novo para o mais antigo
        eq = p.get('equipment') or {}
        vol = eq.get('tank_volume')
        for x in p.get('plantations') or []:
            if not x.get('area'): continue
            for i in ins:
                uq, ud = UNID.get(i.get('sought_dosage_unit'), ('', ''))
                dose_apl = i.get('applied_dosage_value') if i.get('applied_dosage_value') is not None else i.get('sought_dosage_value')
                csv.append({'ap': code, 'ins': i['input']['name'], 'tal': nomes.get(x['plantation_id'], ''),
                            'ini': ini, 'fim': fim, 'fin': carimbo(a['closed_date']),
                            'ha': br(x['area']), 'dsol': br(i.get('sought_dosage_value') or 0, 5), 'un': ud,
                            'qapl': br((dose_apl or 0) * x['area'], 4), 'uq': uq, 'vaz': '',
                            'eq': eq.get('name') or '', 'bico': bico.get(eq.get('id')) or bico0,
                            'vol': br(vol) if vol else '', 'resp': (a.get('responsible') or {}).get('name') or '',
                            'enc': (a.get('charge') or {}).get('name') or ''})

# Semeadura e ciclo das variedades: data de plantio de cada cultivo (Talhões e Cultivos)
sem, ciclos = [], collections.defaultdict(list)
for p in P:
    if not p.get('date'): continue
    sem.append({'t': NOME(p['name']), 'dp': dbr(p['date']), 'ha': str(p['area']), 'v': p.get('variety_name') or '',
                'c': p.get('culture_name') or '', 'area': str((p.get('plot') or {}).get('area') or p['area']),
                'ciclo': str(p.get('cycle') or ''), 's': p.get('state') or ''})
    if p.get('harvest_prediction_date') and p.get('variety_name'):
        ciclos[p['variety_name']].append((dt.date.fromisoformat(p['harvest_prediction_date'][:10]) - dt.date.fromisoformat(p['date'][:10])).days)
vars_ = [{'n': v, 'd': {'14106': round(statistics.median(l))}} for v, l in ciclos.items()]

out = {'gerado': dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z'), 'origem': 'conector Farmbox (API)',
       'aps': aps, 'pp': pp, 'csv': csv, 'sem': sem, 'vars': vars_}
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
print(f"{len(aps)} APs ({sum(a['status']=='finalized' for a in aps.values())} finalizadas), {len(csv)} linhas de histórico, "
      f"{len(sem)} cultivos, {len(vars_)} variedades")
