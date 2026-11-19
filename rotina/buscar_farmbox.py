#!/usr/bin/env python3
"""Busca no Farmbox (API REST oficial) as APs e as plantations da fazenda e grava nos mesmos arquivos que o
coletor_api.py lê (antes eles vinham do conector do Claude).

Uso: python buscar_farmbox.py <pasta_paginas> <plantations.json>

A chave vem da variável de ambiente FARMBOX_TOKEN (Secret do GitHub). Ela NUNCA é impressa nem gravada.
Opcionais: FARMBOX_BASE (padrão https://farmbox.cc), FARMBOX_FARM (14106 = Bom Jesus), FARMBOX_HARVEST (6293 = safra 2026/27).
Só faz leitura (GET)."""
import os, sys, json, time, glob, urllib.request, urllib.error

BASE = os.environ.get('FARMBOX_BASE', 'https://farmbox.cc').rstrip('/')
FARM = os.environ.get('FARMBOX_FARM', '14106')
HARVEST = os.environ.get('FARMBOX_HARVEST', '6293')
TOKEN = os.environ.get('FARMBOX_TOKEN', '').strip()
PASTA, PLANT = sys.argv[1:3]

if not TOKEN:
    sys.exit('FARMBOX_TOKEN vazio: cadastre a chave nos Secrets do repositório.')

# A documentação não diz como a chave vai no cabeçalho; testa as formas comuns na primeira chamada e guarda a que funcionar.
FORMAS = [lambda t: t, lambda t: 'Bearer ' + t, lambda t: 'Token ' + t, lambda t: 'Token token=' + t]
forma = None


def get(path, tentativas=3):
    """GET na API; devolve (status, texto). Repete em caso de 429/5xx/queda de rede."""
    global forma
    url = BASE + path
    ordem = [forma] if forma is not None else range(len(FORMAS))
    ultimo = (0, '')
    for idx in ordem:
        for n in range(tentativas):
            req = urllib.request.Request(url, headers={'Authorization': FORMAS[idx](TOKEN), 'Accept': 'application/json',
                                                       'User-Agent': 'painel-defensivos'})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    forma = idx
                    return r.status, r.read().decode('utf-8')
            except urllib.error.HTTPError as e:
                corpo = e.read().decode('utf-8', 'replace')[:300]
                ultimo = (e.code, corpo)
                if e.code in (401, 403):
                    break                       # forma de autenticação errada: tenta a próxima
                if e.code == 429 or e.code >= 500:
                    time.sleep(5 * (n + 1)); continue
                return e.code, corpo
            except (urllib.error.URLError, TimeoutError) as e:
                ultimo = (0, str(e)[:300]); time.sleep(5 * (n + 1))
    return ultimo


def pagina(path):
    st, txt = get(path)
    if st != 200:
        sys.exit('Farmbox respondeu HTTP %s em %s\n%s' % (st, path.split('?')[0], txt))
    try:
        return txt, json.loads(txt[txt.index('{'):])
    except ValueError:
        sys.exit('Resposta do Farmbox não é JSON em %s: %s' % (path.split('?')[0], txt[:200]))


def todas(rota, params, chave, tam):
    """Percorre todas as páginas de uma lista; devolve [(texto_bruto, json), ...] e confere o total."""
    base = '/api/v1/%s?%s&page_size=%d' % (rota, params, tam)
    t1, j1 = pagina(base + '&page=1')
    pg = j1.get('pagination') or {}
    paginas = [(t1, j1)]
    for p in range(2, int(pg.get('total_pages') or 1) + 1):
        paginas.append(pagina('%s&page=%d' % (base, p)))
    n = sum(len(j[chave]) for _, j in paginas)
    if pg.get('total_entries') is not None and n != int(pg['total_entries']):
        sys.exit('%s: veio %d registros, mas o Farmbox diz que são %s' % (rota, n, pg['total_entries']))
    return paginas


os.makedirs(PASTA, exist_ok=True)
for f in glob.glob(os.path.join(PASTA, '*')):
    os.remove(f)

contagem = {}
for status, prefixo in (('sought', 'sought'), ('finalized', 'fin')):
    pgs = todas('applications', 'from_farm_id=%s&harvest_id=%s&status=%s' % (FARM, HARVEST, status), 'applications', 100)
    for i, (txt, _) in enumerate(pgs, 1):
        open(os.path.join(PASTA, '%s_%03d.json' % (prefixo, i)), 'w', encoding='utf-8').write(txt)
    contagem[status] = sum(len(j['applications']) for _, j in pgs)

pl = todas('plantations', 'farm_id=%s&from_harvest_ids=%s' % (FARM, HARVEST), 'plantations', 100)
json.dump({'plantations': [p for _, j in pl for p in j['plantations']]}, open(PLANT, 'w', encoding='utf-8'), ensure_ascii=False)

total = contagem['sought'] + contagem['finalized']
print('Farmbox: %d APs em aberto, %d finalizadas, %d plantations' % (contagem['sought'], contagem['finalized'],
                                                                   sum(len(j['plantations']) for _, j in pl)))
if total <= 50:
    sys.exit('Poucas APs (%d): algo está errado na busca; nada foi publicado.' % total)


# Movimentações de estoque (3º argumento opcional): usadas só para calcular saldos. Falhar aqui NÃO impede a atualização do painel.
if len(sys.argv) > 3:
    PASTA_MOV = sys.argv[3]
    try:
        os.makedirs(PASTA_MOV, exist_ok=True)
        for f in glob.glob(os.path.join(PASTA_MOV, '*')):
            os.remove(f)
        mv = todas('movimentations', 'farm_id=%s&view=minimal' % FARM, 'movimentations', 100)
        for i, (txt, _) in enumerate(mv, 1):
            open(os.path.join(PASTA_MOV, 'mov_%03d.json' % i), 'w', encoding='utf-8').write(txt)
        print('Farmbox: %d movimentações de estoque' % sum(len(j['movimentations']) for _, j in mv))
    except SystemExit as e:
        for f in glob.glob(os.path.join(PASTA_MOV, '*')):
            os.remove(f)                 # sem histórico completo não calcula saldo (evita alerta falso)
        print('AVISO: movimentações de estoque não buscadas (%s); a simulação de estoque será pulada.' % e)
