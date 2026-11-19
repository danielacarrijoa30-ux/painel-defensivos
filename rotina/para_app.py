"""python3 para_app.py <Paineis_Defensivos_...html> <pasta_app>
Gera o APP (PWA) do painel: index.html + manifest + service worker (abre sem internet) + ícones.
Usa a tela inicial/menu guardados em para_artifact.py (mesma pasta). Depois é só subir a pasta no GitHub Pages."""
import re, sys, os, base64, zlib, io, json, hashlib
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from para_artifact import aliviar, faixa_alertas
src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
h = open(src, encoding='utf-8').read()
pa = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'para_artifact.py'), encoding='utf-8').read()
dec = lambda k: zlib.decompress(base64.b64decode(re.search(k + r' = "([^"]+)"', pa).group(1))).decode('utf-8')
EXTRA, RODAPE = dec('EXTRA_B64'), dec('RODAPE_B64')
# tela inicial + rodapé novo
i = h.rfind('</main>'); j = h.find('<footer', i); k = h.find('</footer>', j)
h = h[:i] + EXTRA + '\n</main>' + h[i+7:j] + RODAPE + h[k+9:]
h = aliviar(h)   # ficha das APs guardada uma vez só (limite de 16 MB do Artifact / tamanho do app)
try:
    h = faixa_alertas(h, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'estoque.json'))   # faixa de estoque (se houver estoque.json)
except Exception as e:
    print('aviso: faixa de alertas não aplicada:', e)
# base (data/hora dos dados)
base = (re.search(r'id="base">([^<]*)<', h) or [None, ''])[1]
ver = hashlib.md5((h+'chipfecha2').encode()).hexdigest()[:10]
# botão Atualizar: recarrega buscando a versão nova
h = re.sub(r'(<a class="btatu") href="[^"]*" target="_top"', r'\1 href="./?v=' + ver + '"', h)
HEAD = ('<link rel="manifest" href="manifest.webmanifest"><meta name="theme-color" content="#3D6421">'
        '<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">'
        '<meta name="apple-mobile-web-app-title" content="Defensivos BJ"><link rel="apple-touch-icon" href="icon-192.png"><link rel="icon" href="icon-192.png">')
h = h.replace('</head>', HEAD + '</head>', 1)
JS = """<style>.offbar{position:fixed;left:0;right:0;bottom:0;z-index:9999;background:#C79A2E;color:#1F3D2E;font:600 13px system-ui,sans-serif;text-align:center;padding:7px 10px;display:none}</style>
<div class="offbar" id="offbar">Sem internet · mostrando os dados de BASE_TXT</div>
<script>
(function(){
  var bar=document.getElementById('offbar');
  function st(){ bar.style.display = navigator.onLine ? 'none' : 'block'; }
  addEventListener('online', st); addEventListener('offline', st); st();
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').then(function(r){ r.update(); });
    var rec=false; navigator.serviceWorker.addEventListener('controllerchange', function(){ if(!rec){ rec=true; } });
  }
  // quando volta a internet ou o app volta para a frente, confere se há versão nova
  function checa(){ if(!navigator.onLine) return; fetch('versao.json?t='+Date.now(),{cache:'no-store'}).then(function(r){return r.json()}).then(function(v){ if(v.ver && v.ver!=='VER'){ location.reload(); } }).catch(function(){}); }
  document.addEventListener('visibilitychange', function(){ if(document.visibilityState==='visible') checa(); });
  addEventListener('online', checa);
})();
</script>
<script>
document.addEventListener('click', function(e){ var l = e.target.closest && e.target.closest('.vmenu label.chip'); if (!l) return; var d = l.closest('.vmenu');
  var nm = l.textContent.replace(/\\s*\\d+\\s*$/, '').trim(); var sm = d.querySelector('summary small'); if (sm) sm.textContent = nm === 'Todos' ? 'toque para filtrar' : '· ' + nm;
  [].forEach.call(d.parentNode.querySelectorAll('.vmenu'), function(m){ if (m !== d) { var q = m.querySelector('summary small'); if (q) q.textContent = 'toque para filtrar'; m.open = false; } });
  setTimeout(function(){ d.open = false; }, 0); });
</script>
<script>
document.addEventListener('click', function(e){
  var f = e.target.closest && e.target.closest('#apsheet [data-x]'); if (f) { var o = document.getElementById('apsheet'); if (o) o.remove(); return; }
  var l = e.target.closest && e.target.closest('.aplink'); if (!l) return;
  var src = document.querySelector('#apdata [data-ap="' + l.getAttribute('data-ap') + '"]'); if (!src) return;
  var old = document.getElementById('apsheet'); if (old) old.remove();
  var o = document.createElement('div'); o.id = 'apsheet'; o.setAttribute('data-x', '1');
  o.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.45);display:flex;align-items:flex-end;justify-content:center';
  o.innerHTML = '<div style="background:#fff;width:100%;max-width:640px;max-height:88vh;overflow:auto;border-radius:18px 18px 0 0;padding:14px 16px 24px;box-shadow:0 -6px 24px rgba(0,0,0,.25)"><div style="text-align:right"><button data-x="1" style="border:0;background:#3D6421;color:#fff;border-radius:16px;padding:6px 14px;font:600 13px system-ui">Fechar ✕</button></div>' + src.innerHTML + '</div>';
  o.addEventListener('click', function(ev){ if (ev.target === o) o.remove(); });
  document.body.appendChild(o);
});
</script>
<script>
document.addEventListener('toggle', function(e){ var d = e.target; if (!d.matches || !d.matches('#talhoes details.tal, #variedades details.tal, #variedades details.tlv')) return;
  var cls = d.classList.contains('tlv') ? 'tlv' : 'tal'; var sib = Array.prototype.filter.call(d.parentNode.children, function(x){ return x !== d && x.tagName === 'DETAILS' && x.classList.contains(cls); });
  sib.forEach(function(x){ x.style.display = d.open ? 'none' : ''; });
  if (d.open) { var r = d.getBoundingClientRect(); if (r.top < 0 || r.top > 300) d.scrollIntoView({block: 'start'}); } }, true);
</script>""".replace('BASE_TXT', base).replace('VER', ver)
# botão ⟳ Atualizar: com o endereço do "disparador" (atualizar_url.txt) ele pede ao GitHub para rodar a rotina inteira
# (Farmbox → painel → app) e recarrega sozinho quando sai a versão nova; sem o endereço, só recarrega a página como antes.
try:
    EP = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'atualizar_url.txt'), encoding='utf-8').read().strip()
except OSError:
    EP = ''
BTN = """<script>
(function(){
  var EP='ATU_ENDPOINT', cur='VERSAO_ATUAL';
  var bt=document.querySelector('header .btatu'); if(!bt||!EP) return;
  var busy=false;
  function btns(){ return [].slice.call(document.querySelectorAll('.btatu,.hatu')); }
  function lab(t){ btns().forEach(function(b){ b.textContent=t; }); }
  function msg(t){ var m=document.getElementById('atumsg');
    if(!m){ m=document.createElement('div'); m.id='atumsg';
      m.style.cssText='position:fixed;left:12px;right:12px;bottom:12px;z-index:9998;background:#1F3D2E;color:#fff;border-radius:12px;padding:10px 14px;font:600 13px system-ui,sans-serif;text-align:center;box-shadow:0 4px 16px rgba(0,0,0,.3)';
      document.body.appendChild(m); }
    m.textContent=t; m.style.display=t?'block':'none'; }
  bt.addEventListener('click',function(ev){
    if(busy||!navigator.onLine) return;
    ev.preventDefault(); busy=true; lab('⟳ Atualizando…');
    msg('Buscando os dados novos no Farmbox… leva uns 5 minutos. O painel recarrega sozinho quando terminar.');
    try{ fetch(EP,{method:'POST',mode:'no-cors',headers:{'Content-Type':'text/plain'},body:'atualizar'}); }catch(e){}
    var t0=Date.now();
    var iv=setInterval(function(){
      fetch('versao.json?t='+Date.now(),{cache:'no-store'}).then(function(r){return r.json()}).then(function(v){
        if(v.ver&&v.ver!==cur){ clearInterval(iv); location.reload(); } }).catch(function(){});
      if(Date.now()-t0>10*60000){ clearInterval(iv); busy=false; lab('⟳ Atualizar');
        msg('Ainda não saiu a versão nova. Toque em Atualizar de novo daqui a pouco.'); setTimeout(function(){ msg(''); },7000); }
    },15000);
  });
})();
</script>""".replace('ATU_ENDPOINT', EP).replace('VERSAO_ATUAL', ver)
i = h.rfind('</body>'); h = h[:i] + JS + '\n' + BTN + '\n' + h[i:]
open(os.path.join(out, 'index.html'), 'w', encoding='utf-8').write(h)
open(os.path.join(out, 'versao.json'), 'w').write(json.dumps({'ver': ver, 'base': base}))
SW = """// service worker do app Defensivos Bom Jesus — rede primeiro, cache se estiver sem internet
const C='defensivos-bj';
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(['./','index.html','manifest.webmanifest','icon-192.png','icon-512.png'])));self.skipWaiting();});
self.addEventListener('activate',e=>{e.waitUntil(self.clients.claim());});
self.addEventListener('fetch',e=>{
  const r=e.request; if(r.method!=='GET') return;
  const u=new URL(r.url); if(u.origin!==location.origin) return;
  if(u.pathname.endsWith('versao.json')) return;           // sempre da rede
  e.respondWith(fetch(r,{cache:'no-store'}).then(resp=>{ if(resp.ok){const cp=resp.clone(); const key=(r.mode==='navigate')?'index.html':r; caches.open(C).then(c=>c.put(key,cp));} return resp; })
    .catch(()=>caches.match(r.mode==='navigate'?'index.html':r,{ignoreSearch:true}).then(m=>m||caches.match('index.html'))));
});
"""
open(os.path.join(out, 'sw.js'), 'w').write(SW)
open(os.path.join(out, 'manifest.webmanifest'), 'w').write(json.dumps({
  "name": "Aplicações de Defensivos · Fazenda Bom Jesus", "short_name": "Defensivos BJ",
  "start_url": "./", "scope": "./", "display": "standalone", "background_color": "#F3F4EE", "theme_color": "#3D6421",
  "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"}, {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}, ensure_ascii=False))
# ícones a partir da logo embutida
lg = re.search(r'src="data:image/png;base64,([^"]+)"', h)
logo = Image.open(io.BytesIO(base64.b64decode(lg.group(1)))).convert('RGBA')
for s in (192, 512):
    im = Image.new('RGB', (s, s), (31, 61, 46)); w = int(s * 0.62); hh = int(w * logo.height / logo.width)
    if hh > s * 0.72: hh = int(s * 0.72); w = int(hh * logo.width / logo.height)
    im.paste(logo.resize((w, hh), Image.LANCZOS), ((s - w) // 2, (s - hh) // 2), logo.resize((w, hh), Image.LANCZOS))
    im.save(os.path.join(out, f'icon-{s}.png'))
open(os.path.join(out, '.nojekyll'), 'w').write('')
print(json.dumps({'ok': True, 'ver': ver, 'base': base, 'bytes': len(h)}))
