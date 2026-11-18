// DISPARADOR DO BOTÃO "ATUALIZAR" (Google Apps Script)
// Recebe o toque no botão do app e pede ao GitHub para rodar a atualização. A chave de acesso ao GitHub
// fica guardada AQUI (Propriedades do script), nunca na página do app.
// Passo a passo: ver as instruções que o Claude passou (criar o token, colar em GH_TOKEN, implantar como app da Web).

const REPO = 'danielacarrijoa30-ux/painel-defensivos';
const WORKFLOW = 'atualizar.yml';
const BRANCH = 'main';
const INTERVALO_MIN = 3;   // ignora pedidos repetidos dentro desse tempo

function doPost() {
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const props = PropertiesService.getScriptProperties();
    const agora = Date.now();
    if (agora - Number(props.getProperty('ultimo') || 0) < INTERVALO_MIN * 60 * 1000) {
      return resposta({ ok: true, ignorado: 'pedido recente' });
    }
    props.setProperty('ultimo', String(agora));
    const r = UrlFetchApp.fetch('https://api.github.com/repos/' + REPO + '/actions/workflows/' + WORKFLOW + '/dispatches', {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + props.getProperty('GH_TOKEN'),
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
      payload: JSON.stringify({ ref: BRANCH }),
      muteHttpExceptions: true,
    });
    return resposta({ ok: r.getResponseCode() === 204, codigo: r.getResponseCode() });
  } finally {
    lock.releaseLock();
  }
}

function doGet() {
  return resposta({ ok: true, mensagem: 'Disparador do painel no ar.' });
}

function resposta(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
