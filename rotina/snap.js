// node snap.js entrada_tmp.html saida_final.html  -> roda o JavaScript do painel e salva o HTML pronto, sem scripts (abre no WhatsApp)
const {chromium} = require('playwright'); const fs = require('fs'); const path = require('path');

// --- enxugar (12/11/2026): troca style="..." repetidos por classes CSS (!important) e colapsa espacos; visual identico, so reduz o tamanho (limite do Artifact: 16 MB)
function enxugar(h) {
  const TAG = /<[a-zA-Z][^\s/>]*(?:\s+[^\s=>/]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?)*\s*\/?>/g;
  const STY = /\sstyle="([^"]*)"/, CLS = /\sclass="([^"]*)"/;
  const decls = v => { const out = []; let cur = '', d = 0; for (const ch of v) { if (ch === '(') d++; else if (ch === ')') d--; if (ch === ';' && d === 0) { out.push(cur); cur = ''; } else cur += ch; } out.push(cur); return out.map(x => x.trim()).filter(x => x); };
  const cnt = new Map();
  for (const m of h.matchAll(TAG)) { const s = STY.exec(m[0]); if (s) cnt.set(s[1], (cnt.get(s[1]) || 0) + 1); }
  const names = new Map(), css = [];
  for (const [v, c] of [...cnt.entries()].sort((a, b) => b[0].length * b[1] - a[0].length * a[1])) {
    if (c < 2 || v.length < 14 || v.includes('url(') || v.includes('data:') || v.includes('!important') || v.includes('{') || v.includes('}')) continue;
    const ds = decls(v); if (ds.some(d => !d.includes(':'))) continue;
    const nm = 'zq' + names.size.toString(16); names.set(v, nm);
    css.push('.' + nm + '{' + ds.map(d => d + '!important').join(';') + '}');
  }
  h = h.replace(TAG, t => {
    const s = STY.exec(t); if (!s || !names.has(s[1])) return t;
    const nm = names.get(s[1]); t = t.slice(0, s.index) + t.slice(s.index + s[0].length);
    const c = CLS.exec(t);
    if (c) return t.slice(0, c.index) + ' class="' + c[1] + ' ' + nm + '"' + t.slice(c.index + c[0].length);
    const head = t.split('>')[0]; const i = head.includes(' ') ? t.indexOf(' ') : (t.endsWith('/>') ? t.length - 2 : t.length - 1);
    return t.slice(0, i) + ' class="' + nm + '"' + t.slice(i);
  });
  h = h.split(/(<style[^>]*>[\s\S]*?<\/style>|<pre[\s\S]*?<\/pre>|<textarea[\s\S]*?<\/textarea>)/).map(p => /^<(style|pre|textarea)/.test(p) ? p : p.replace(/\s{2,}/g, m => m.includes('\n') ? '\n' : ' ')).join('');
  const k = h.lastIndexOf('</head>');
  return h.slice(0, k) + '<style>' + css.join('') + '</style>' + h.slice(k);
}
(async () => {
  const [inp, out] = process.argv.slice(2);
  const b = await chromium.launch(); const p = await b.newPage(); const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  await p.goto('file://' + path.resolve(inp));
  const html = await p.evaluate(() => { document.querySelectorAll('script').forEach(s => s.remove()); return '<!doctype html>\n' + document.documentElement.outerHTML; });
  fs.writeFileSync(out, enxugar(html));
  const c = await b.newContext({javaScriptEnabled: false}); const q = await c.newPage();
  await q.goto('file://' + path.resolve(out));
  const ok = await q.evaluate(() => !!document.querySelector('#s-resumo') && document.querySelectorAll('.sec').length === 17);
  console.log(JSON.stringify({erros: errs, ok, bytes: fs.statSync(out).size}));
  await b.close(); if (errs.length || !ok) process.exit(1);
})();
