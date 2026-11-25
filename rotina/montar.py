#!/usr/bin/env python3
"""Monta o painel de defensivos (Fazenda Bom Jesus) a partir do coleta_farmbox.json.
Uso: python3 montar.py coleta_farmbox.json template.html saida_tmp.html
Depois: node snap.js saida_tmp.html Paineis_Defensivos_BomJesus_DD-MM-AAAA.html  (gera o HTML final, sem JavaScript)"""
import json, re, sys, math, collections, datetime as dt

ARQ, TPL, OUT = sys.argv[1:4]
C = json.load(open(ARQ, encoding='utf-8'))
TZ = dt.timezone(dt.timedelta(hours=-3))
agora = dt.datetime.fromisoformat(C['gerado'].replace('Z', '+00:00')).astimezone(TZ)
HOJE = agora.date()
EXCL_ATIV = {'Adubação', 'Corretivo'}
UN = {'l_ha': 'L/ha', 'kg_ha': 'kg/ha'}

def num(s):
    s = (s or '').strip()
    if not s: return None
    return float(s.replace('.', '').replace(',', '.'))

def tal_nome(t):
    t = (t or '').strip().upper()
    t = {'P5 AMILTA': 'P5/AMILTA', 'P1/2/3': 'P1/P2/P3'}.get(t, t)
    return t

def dbr_iso(s):
    m = re.match(r'(\d\d)/(\d\d)/(\d{4})', s or '')
    return f'{m.group(3)}-{m.group(2)}-{m.group(1)}' if m else None

# ---------- CSV do histórico ----------
csvap = collections.defaultdict(lambda: {'ins': collections.OrderedDict()})
eqvol = {}
cnt = collections.Counter()
for r in C['csv']:
    a = csvap[r['ap']]
    for k in ('vaz', 'eq', 'bico', 'vol', 'resp'):
        if r.get(k): a[k] = r[k]
    i = a['ins'].setdefault(r['ins'], {'dsol': r['dsol'], 'un': r['un'], 'qapl': 0.0})
    if r['qapl']: i['qapl'] += num(r['qapl']) or 0
    if r['eq'] and r['vol']: eqvol[r['eq']] = num(r['vol'])
    key = (r['ap'], tal_nome(r['tal']), r['eq'], r['ini'], r['fim'], r['fin'], r['ha'], r['resp'], r['enc'])
    cnt[(key, r['ins'])] += 1
mult = collections.defaultdict(int)
for (key, ins), n in cnt.items(): mult[key] = max(mult[key], n)
apont = []
for key, m in mult.items():
    ap, tal, eq, ini, fim, fin, ha, resp, enc = key
    if not ha: continue
    apont.append({'ap': ap, 't': tal, 'eq': eq or 'Não informado', 'ini': dbr_iso(ini), 'fim': dbr_iso(fim),
                  'ha': round((num(ha) or 0) * m, 2), 'resp': resp, 'enc': enc})
datas = collections.defaultdict(lambda: [None, None])   # (ap, talhão) -> [início, fim]
for x in apont:
    d = datas[(x['ap'], x['t'])]
    if x['ini'] and (not d[0] or x['ini'] < d[0]): d[0] = x['ini']
    if x['fim'] and (not d[1] or x['fim'] > d[1]): d[1] = x['fim']

# ---------- página de impressão (PDF) da AP ----------
def parse_pp(s):
    T = (s or '').split('|'); o = {'cargas': [], 'prods': [], 'calda': None}
    for i, x in enumerate(T):
        if x.startswith('Área Solicitada:') and x.strip() != 'Área Solicitada:' and i + 1 < len(T): o['equip'] = T[i + 1]
        m = re.match(r'Vazão:\s*([\d.,]+)\s*L/Ha', x)
        if m: o['vazao'] = num(m.group(1))
        if x.startswith('Vazão') and i > 0 and T[i - 1] != o.get('equip') and not T[i - 1].startswith('Área'): o['bico'] = T[i - 1]
    if 'Insumo' not in T: return o
    ii = T.index('Insumo')
    vi = next((i for i, x in enumerate(T) if x.startswith('Vazão')), None)
    if vi is not None:
        k = vi + 1
        while k < ii and (T[k].startswith('Pressão') or T[k].startswith('Velocidade')): k += 1
        while k + 2 < ii and re.match(r'^\d+x$', T[k]):
            o['cargas'].append([int(T[k][:-1]), num(T[k + 1].split()[0]), num(T[k + 2].split()[0])]); k += 3
    ci = T.index('Calda total') if 'Calda total' in T else len(T)
    k = ii + 1
    while k < ci:
        nome = T[k]; tipo = T[k + 1] if k + 1 < ci else ''; k += 2; pt = []; tot = None
        while k < ci:
            x = T[k]
            if re.match(r'^\d+x$', x) and k + 1 < ci: pt.append([int(x[:-1]), T[k + 1]]); k += 2; continue
            if x == '-': k += 1; continue
            tot = x; k += 1; break
        o['prods'].append({'nome': nome, 'tipo': tipo, 'pt': pt, 'tot': tot})
    k = ci + 1; cal = 0; ok = False
    while k + 1 < len(T) and re.match(r'^\d+x$', T[k]):
        cal += int(T[k][:-1]) * (num(T[k + 1].split()[0]) or 0); k += 2; ok = True
    if ok: o['calda'] = cal
    return o

# ---------- APs ----------
aps = []
for code, a in C['aps'].items():
    ativ = a.get('ativ') or 'Não informado'
    if ativ in EXCL_ATIV: continue
    if any('CANA' in (t['t'] or '').upper() for t in a['tal']): continue
    fin = a.get('status') == 'finalized'
    # Ajuste 25/11/2026 (pedido da Daniela): AP em aberto com a área total já lançada pelos operadores
    # (>= 99,5% da área solicitada) aparece como CONCLUÍDA no painel, mesmo antes da movimentação de
    # estoque e da finalização da AP no Farmbox.
    sol_t = sum(t.get('sol') or 0 for t in a['tal']); apl_t = sum(t.get('apl') or 0 for t in a['tal'])
    concl_area = (not fin) and sol_t > 0 and apl_t >= 0.995 * sol_t
    fim_prog = max([x['d'] for x in (a.get('prog') or []) if x.get('d')] or [None]) if concl_area else None
    fin = fin or concl_area
    dsol = a.get('date')
    tal = []
    for t in a['tal']:
        nm = tal_nome(t['t']); ini, fim = datas.get((code, nm), [None, None])
        dias = None
        if not fin and dsol:
            dias = max(0, (HOJE - dt.date.fromisoformat(dsol)).days)
        if concl_area and not fim: fim = fim_prog
        if concl_area and not ini: ini = fim_prog
        tal.append({'t': nm, 'sit': 'Finalizada' if fin else 'Atrasada', 'ini': ini, 'fim': fim if fin else None,
                    'rec': round(t.get('sol') or 0, 2), 'solc': round(t.get('sol') or 0, 2),
                    'apl': round(t.get('apl') or 0, 2), 'dias': dias})
    area = sum(t['solc'] for t in tal)
    p = parse_pp(C['pp'].get(code, '')); cv = csvap.get(code)
    det = {'equip': p.get('equip') or (cv or {}).get('eq'), 'bico': p.get('bico') or (cv or {}).get('bico'),
           'vazao': p.get('vazao') or (num(cv['vaz']) if cv and cv.get('vaz') else None), 'area': round(area, 2)}
    det['vol'] = (num(cv['vol']) if cv and cv.get('vol') else None) or eqvol.get(det['equip'] or '')
    if det['vol'] and det['vol'] < 100: det['vol'] = None
    det['cargas'] = p['cargas']; det['tanques'] = sum(x[0] for x in p['cargas']) or None
    det['calda'] = p['calda'] or (det['vazao'] * area if det['vazao'] else None)
    if not det['tanques'] and det['calda'] and det['vol']: det['tanques'] = math.ceil(det['calda'] / det['vol'])
    if cv and cv.get('resp'): det['resp'] = cv['resp']
    ins = {i['n']: i for i in a.get('ins', [])}
    pp = {x['nome']: x for x in p['prods']}
    nomes = [x['nome'] for x in p['prods']] or list(ins)
    prods = []
    for n in nomes:
        x = pp.get(n, {}); i = ins.get(n, {}); c = (cv or {'ins': {}})['ins'].get(n)
        tot = un = None
        if x.get('tot'):
            m = re.match(r'([\d.,]+)\s*(\S+)', x['tot'])
            if m: tot = num(m.group(1)); un = m.group(2)
        if tot is None and i.get('q') is not None: tot = i['q']
        dose = ud = None
        if i.get('dose') is not None: dose = i['dose']; ud = UN.get(i.get('un'), i.get('un'))
        elif c and c.get('dsol'): dose = num(c['dsol']); ud = (c['un'] or '').replace('Ha', 'ha')
        elif tot is not None and area: dose = tot / area; ud = UN.get(i.get('un'), (un or '') + '/ha')
        if un is None: un = (ud or '').split('/')[0]
        pr = {'nome': n, 'tipo': x.get('tipo') or i.get('tipo', ''), 'dose': dose, 'ud': ud, 'tot': tot, 'un': un,
              'pt': [[q[0], q[1]] for q in x.get('pt', [])]}
        if fin and c and c['qapl']: pr['apl'] = round(c['qapl'], 3)
        prods.append(pr)
    det['prods'] = prods
    aps.append({'ap': code, 'n': int(code[2:]), 'ativ': ativ, 'dsol': dsol, 'tal': tal,
                'prod': '; '.join(pr['nome'] for pr in prods), 'eq': det['equip'] or '', 'id': a['id'],
                'sit': 'Finalizada' if fin else 'Atrasada', 'concl_area': concl_area, 'det': det})
aps.sort(key=lambda a: -a['n'])
# ---------- estádio estimado pela data de plantio (Operações > Semeadura + ciclo da variedade) ----------
FAZ_ID = '14106'   # Bom Jesus no cadastro de variedades do Farmbox
CICLO = {v['n'].strip().upper(): (v.get('d') or {}).get(FAZ_ID) for v in C.get('vars', [])}
def estadio(das, ciclo):
    c = ciclo or 115
    if das < 0: return 'Não semeado'
    if das < 5: return 'Semeado'
    for lim, e in ((8, 'VE'), (12, 'VC'), (17, 'V1'), (22, 'V2'), (27, 'V3'), (32, 'V4'), (37, 'V5')):
        if das < lim: return e
    for f, e in ((0.40, 'V6+'), (0.46, 'R1'), (0.55, 'R2'), (0.63, 'R3'), (0.72, 'R4'), (0.84, 'R5'), (0.93, 'R6'), (1.0, 'R7')):
        if das < f * c: return e
    return 'R8'
def dfmt(s):
    m = re.match(r'(\d\d)/(\d\d)/(\d{4})', s or ''); return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None
gs = collections.defaultdict(lambda: {'area': 0, 'vars': collections.defaultdict(list)})
for x in C.get('sem', []):
    if (x.get('c') or 'Soja') != 'Soja': continue
    t = tal_nome(x['t']); g = gs[t]
    try: g['area'] = max(g['area'], float(x.get('area') or 0))
    except ValueError: pass
    d0 = dfmt(x.get('dp'))
    try: ha = float(x.get('ha') or 0)
    except ValueError: ha = 0
    if d0 and ha > 0: g['vars'][(x.get('v') or '').strip()].append((d0, ha))
est = []
for t, g in gs.items():
    vs = []
    for v, l in g['vars'].items():
        ha = sum(h for _, h in l); dm = dt.date.fromordinal(round(sum(d.toordinal() * h for d, h in l) / ha))
        cic = CICLO.get(v.upper())
        das = (HOJE - dm).days
        vs.append({'v': v, 'ha': round(ha, 2), 'dmed': dm.isoformat(), 'dmin': min(d for d, _ in l).isoformat(), 'dmax': max(d for d, _ in l).isoformat(),
                   'ciclo': cic, 'das': das, 'est': estadio(das, cic),
                   'r1': (dm + dt.timedelta(days=round(0.40 * (cic or 115)))).isoformat(), 'colh': (dm + dt.timedelta(days=cic or 115)).isoformat()})
    if not vs: continue
    vs.sort(key=lambda x: -x['ha'])
    sem_ha = sum(x['ha'] for x in vs)
    est.append({'t': t, 'area': round(g['area'], 2), 'sem': round(sem_ha, 2), 'pct': min(1, sem_ha / g['area']) if g['area'] else None, 'v': vs})
est.sort(key=lambda x: x['v'][0]['dmed'])
# ---------- produtos aplicados (apontamentos do histórico: hectares do talhão x dose recomendada) ----------
prodapl = []
for r in C['csv']:
    ha = num(r['ha']); ds = num(r['dsol'])
    if not ha or ds is None: continue
    prodapl.append({'p': (r['ins'] or '').strip(), 'ap': r['ap'], 't': tal_nome(r['tal']), 'd': dbr_iso(r['fim']) or dbr_iso(r['ini']),
                    'ha': round(ha, 2), 'dose': ds, 'un': (r['un'] or '').split('/')[0].replace('Kg', 'kg'), 'q': round(ha * ds, 3), 'eq': r['eq'] or ''})
# ---------- lançamentos de área das APs em aberto (com data) ----------
apab = []
for k, a in C['aps'].items():
    if a.get('status') == 'finalized': continue
    for x in a.get('prog') or []:
        if x.get('ha') and x.get('d'): apab.append({'ap': k, 't': tal_nome(x.get('t')), 'fim': x['d'], 'ha': round(float(x['ha']), 2), 'eq': x.get('eq') or ''})
D = {'gerado': agora.strftime('%d/%m/%Y'), 'base': agora.strftime('%d/%m/%Y %H:%M'), 'hoje': HOJE.isoformat(),
     'aps': aps, 'apont': apont, 'est': est, 'prod': prodapl, 'apab': apab}
open(OUT, 'w', encoding='utf-8').write(open(TPL, encoding='utf-8').read().replace('__DADOS__', json.dumps(D, ensure_ascii=False)))
print(f"{len(aps)} APs ({sum(a['sit']=='Finalizada' for a in aps)} concluídas, sendo {sum(1 for a in aps if a.get('concl_area'))} com área completa ainda não finalizadas no Farmbox: {', '.join(a['ap'] for a in aps if a.get('concl_area')) or '-'}), {len(apont)} apontamentos, base {D['base']}")
