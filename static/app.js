'use strict';
// 好奇猴快传：原生网页交互，不依赖前端框架。
const $ = id => document.getElementById(id);
// 每个项目独占自己的 URL 子路径，也兼容单独部署在域名根目录。
const appRoot = new URL('./', location.href).pathname;
const appUrl = path => appRoot + path.replace(/^\/+/, '');
let selectedFile = null;
let pickupUrl = '';
const HISTORY_KEY = 'hamoki-transfer-sent-v1';
const historyTtl = { '1h': 3600, '24h': 86400, '7d': 604800 };

function readSentHistory() {
  try {
    const rows = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    return Array.isArray(rows) ? rows.filter(row =>
      row && typeof row.code === 'string' && /^(?:[0-9A-HJ-NP-Z]{4}|[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{12})$/.test(row.code)
    ).slice(0, 60) : [];
  } catch { return []; }
}
function rememberSent(item) {
  const previous = readSentHistory().filter(row => row.code !== item.code);
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify([item, ...previous].slice(0, 60))); }
  catch { flash('上传成功，但浏览器不允许保存历史记录。请先复制取件码。'); }
}
function formatWhen(seconds) {
  const date = new Date(seconds * 1000);
  return Number.isFinite(date.valueOf()) ? date.toLocaleString('zh-CN', { hour12: false }) : '未知时间';
}
function displayDone(item) {
  pickupUrl = location.origin + appRoot + '?code=' + encodeURIComponent(item.code);
  // The long random public link does not expose the easy-to-type pickup code.
  const publicPath = typeof item.public_path === 'string' && /^\/f\/[A-Za-z0-9_-]{16,64}$/.test(item.public_path)
    ? item.public_path.substring(1)
    : (item.has_file && !item.has_text ? 'd/' + encodeURIComponent(item.code) : '?code=' + encodeURIComponent(item.code));
  const publicUrl = location.origin + appRoot + publicPath;
  $('public-link-url').textContent = publicUrl;
  $('public-link-url').href = publicUrl;
  $('copy-public-link').dataset.url = publicUrl;
  $('copy-public-link').textContent = '复制';
  $('public-link-tip').textContent = item.public_path
    ? '发给别人就能直接领取，无需输入取件码。'
    : '旧记录使用原来的领取链接，新上传会生成直接访问的公共链接。';
  $('done-code').textContent = item.code;
  $('done-qr').src = appUrl('api/qr/' + encodeURIComponent(item.code));
  $('copy-link').textContent = '复制领取链接';
  pane('done');
}
function renderHistory() {
  const target = $('history-list');
  target.replaceChildren();
  const rows = readSentHistory();
  if (!rows.length) {
    const empty = document.createElement('p');
    empty.className = 'history-empty';
    empty.textContent = '还没有上传记录，发送成功后会自动保存在这里。';
    target.append(empty);
    return;
  }
  for (const item of rows) {
    const expired = Number(item.expires) <= Math.floor(Date.now() / 1000);
    const row = document.createElement('div');
    row.className = 'history-item';
    const info = document.createElement('div');
    info.className = 'history-info';
    const name = document.createElement('strong');
    name.textContent = item.has_file && item.has_text ? item.name + ' + 文字'
      : item.has_file ? item.name : '文字分享';
    const meta = document.createElement('small');
    meta.textContent = item.code + ' · ' + formatWhen(item.created) + (expired ? ' · 已过期' : '');
    info.append(name, meta);
    const button = document.createElement('button');
    button.className = 'secondary history-open';
    button.type = 'button';
    button.textContent = expired ? '已过期' : '查看';
    button.disabled = expired;
    button.addEventListener('click', () => displayDone(item));
    row.append(info, button);
    target.append(row);
  }
}

// Remove obsolete upload keys from earlier private-link versions.
sessionStorage.removeItem('hamoki_upload_key');
if (new URLSearchParams(location.hash.substring(1)).has('key')) {
  history.replaceState(null, '', location.pathname + location.search);
}
$('send-tip').textContent = '无需登录，直接上传 · 文件到期后自动删除';

function flash(message) {
  $('message').textContent = message || '';
}
function pane(name) {
  ['send', 'get', 'history', 'done'].forEach(item => {
    $('pane-' + item).hidden = item !== name;
  });
  for (const tab of ['send', 'get', 'history']) {
    $('tab-' + tab).classList.toggle('active', name === tab);
    $('tab-' + tab).setAttribute('aria-selected', String(name === tab));
  }
  if (name === 'history') renderHistory();
  flash('');
}
function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' 字节';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
  return (bytes / 1073741824).toFixed(2) + ' GB';
}
function setFile(file) {
  selectedFile = file || null;
  $('file-info').textContent = selectedFile
    ? selectedFile.name + ' · ' + formatSize(selectedFile.size) : '';
  $('clear-file').hidden = !selectedFile;
  $('selected-file').hidden = !selectedFile;
}
$('pick').onclick = () => $('file').click();
$('drop').addEventListener('click', event => {
  if (event.target.closest('button')) return;
  $('file').click();
});
$('drop').addEventListener('keydown', event => {
  if (event.target !== $('drop')) return;
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    $('file').click();
  }
});
$('file').onchange = () => setFile($('file').files[0] || null);
$('clear-file').onclick = event => {
  event.stopPropagation();
  $('file').value = '';
  setFile(null);
};
for (const name of ['dragenter', 'dragover']) {
  $('drop').addEventListener(name, event => {
    event.preventDefault();
    $('pick').classList.add('drag');
  });
}
for (const name of ['dragleave', 'drop']) {
  $('drop').addEventListener(name, event => {
    event.preventDefault();
    $('pick').classList.remove('drag');
  });
}
$('drop').addEventListener('drop', event => {
  const file = event.dataTransfer?.files?.[0];
  if (file) setFile(file);
});
$('tab-send').onclick = () => pane('send');
$('tab-get').onclick = () => pane('get');
$('tab-history').onclick = () => pane('history');

async function readJson(response) {
  let body;
  try { body = await response.json(); }
  catch { throw Error('服务器响应异常，请稍后重试'); }
  if (!response.ok) throw Error(body.error || '操作失败，请稍后重试');
  return body;
}
function sendForm(form) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('POST', appUrl('api/send'));
    request.upload.onprogress = event => {
      if (!event.lengthComputable) return;
      const percent = Math.round(event.loaded * 100 / event.total);
      $('progress-bar').value = percent;
      $('upload-percent').textContent = percent + '%';
    };
    request.onerror = () => reject(Error('网络连接中断，请重试'));
    request.onload = () => {
      let body;
      try { body = JSON.parse(request.responseText); }
      catch { reject(Error('服务器响应异常，请稍后重试')); return; }
      if (request.status < 200 || request.status >= 300) {
        reject(Error(body.error || '上传失败，请重试'));
      } else {
        resolve(body);
      }
    };
    request.send(form);
  });
}
$('upload').onclick = async () => {
  const text = $('text').value.trim();
  if (!selectedFile && !text) { flash('请先选择文件，或输入一段文字。'); return; }
  const form = new FormData();
  form.append('ttl', $('ttl').value);
  if (selectedFile) form.append('file', selectedFile);
  if (text) form.append('text', text);
  const button = $('upload');
  button.disabled = true;
  $('upload-progress').hidden = false;
  $('progress-bar').value = 0;
  $('upload-percent').textContent = '0%';
  flash('');
  try {
    const response = await sendForm(form);
    rememberSent({
      code: response.code, name: response.name, has_file: response.has_file,
      has_text: response.has_text, created: response.created, public_path: response.public_path,
      expires: response.expires || response.created + historyTtl[response.ttl]
    });
    displayDone(response);
  } catch (error) {
    flash(error.message);
  } finally {
    button.disabled = false;
    $('upload-progress').hidden = true;
  }
};
async function copyText(value, button, successLabel) {
  try {
    await navigator.clipboard.writeText(value);
    if (button) {
      const previous = button.textContent;
      button.textContent = successLabel;
      window.setTimeout(() => { button.textContent = previous; }, 1800);
    } else {
      flash('取件码已复制');
    }
  } catch {
    flash('复制失败，请检查浏览器剪贴板权限');
  }
}
$('copy-code').onclick = () => copyText($('done-code').textContent, null, '');
$('copy-link').onclick = () => copyText(pickupUrl, $('copy-link'), '已复制');
$('copy-public-link').onclick = () => copyText($('copy-public-link').dataset.url, $('copy-public-link'), '已复制');
$('again').onclick = () => {
  $('file').value = '';
  $('text').value = '';
  setFile(null);
  pane('send');
};

$('lookup').onclick = async () => {
  const code = $('code-input').value.trim().toUpperCase();
  if (!code) { flash('请输入取件码'); return; }
  $('found').hidden = true;
  flash('正在查找…');
  try {
    const info = await readJson(await fetch(appUrl('api/item/' + encodeURIComponent(code))));
    const hasFile = info.has_file ?? info.kind === 'file';
    const hasText = info.has_text ?? info.kind === 'text';
    $('found-name').textContent = hasFile && hasText ? info.name + ' · 附带文字' : info.name;
    $('found-details').textContent = hasFile && hasText
      ? formatSize(info.size) + ' · 图片/文件和文字都可领取 · 剩余 ' + info.remaining + ' 次文件下载'
      : hasFile
        ? formatSize(info.size) + ' · 剩余 ' + info.remaining + ' 次下载'
        : '文字内容 · 剩余 ' + info.remaining + ' 次领取';
    $('claim').dataset.code = code;
    $('claim').hidden = !hasText;
    $('download-file').dataset.code = code;
    $('download-file').hidden = !hasFile;
    $('download-file').textContent = '下载 ' + (hasFile ? info.name : '文件');
    $('received-text').hidden = true;
    $('copy-text').hidden = true;
    $('found').hidden = false;
    flash('');
  } catch (error) {
    flash(error.message);
  }
};
$('claim').onclick = async () => {
  const code = $('claim').dataset.code;
  try {
    const info = await readJson(await fetch(appUrl('api/text/' + encodeURIComponent(code)), { method: 'POST' }));
    $('received-text').textContent = info.text;
    $('received-text').hidden = false;
    $('copy-text').hidden = false;
    flash('');
  } catch (error) {
    flash(error.message);
  }
};
$('download-file').onclick = () => {
  location.href = appUrl('d/' + encodeURIComponent($('download-file').dataset.code));
};
$('copy-text').onclick = () => copyText($('received-text').textContent, $('copy-text'), '已复制');
$('code-input').addEventListener('keydown', event => {
  if (event.key === 'Enter') $('lookup').click();
});
const incoming = new URLSearchParams(location.search).get('code');
if (incoming) {
  pane('get');
  $('code-input').value = incoming;
  $('lookup').click();
} else {
  pane('send');
}
