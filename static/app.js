'use strict';
// 好奇猴快传：原生网页交互，不依赖前端框架。
const $ = id => document.getElementById(id);
// 每个项目独占自己的 URL 子路径，也兼容单独部署在域名根目录。
const appRoot = new URL('./', location.href).pathname;
const appUrl = path => appRoot + path.replace(/^\/+/, '');
let selectedFiles = [];
let selectedMode = 'single';
let pickupUrl = '';
let shareUrl = '';
const HISTORY_KEY = 'hamoki-transfer-sent-v1';
const historyTtl = { '1d': 86400, '3d': 259200, '7d': 604800, '1h': 3600, '24h': 86400 };
const MAX_FILE_BYTES = 5 * 1024 * 1024 * 1024;

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
  shareUrl = publicUrl;
  $('public-link-url').textContent = publicUrl;
  $('public-link-url').href = publicUrl;
  $('copy-public-link').dataset.url = publicUrl;
  $('copy-public-link').textContent = '复制';
  $('public-link-tip').textContent = item.public_path
    ? '发给别人就能直接领取，无需输入取件码。'
    : '旧记录使用原来的领取链接，新上传会生成直接访问的公共链接。';
  $('pane-done').querySelector('[data-expiry-countdown]').dataset.expires = String(item.expires || item.created + historyTtl[item.ttl] || 0);
  window.hamokiRefreshCountdown?.();
  const codeDisplay = $('done-code');
  codeDisplay.replaceChildren();
  codeDisplay.classList.toggle('code-tiles', item.code.length === 4);
  if (item.code.length === 4) {
    for (const character of item.code) {
      const tile = document.createElement('span');
      tile.className = 'code-tile';
      tile.textContent = character;
      codeDisplay.append(tile);
    }
  } else {
    codeDisplay.textContent = item.code;
  }
  $('done-qr').src = appUrl('api/qr/' + encodeURIComponent(item.code));
  $('copy-link').textContent = '复制领取链接';
  $('share-guide').hidden = true;
  $('share-guide-url').value = publicUrl;
  $('share-wechat').setAttribute('aria-pressed', 'false');
  $('share-qq').setAttribute('aria-pressed', 'false');
  pane('done');
}
function isImageName(name) {
  return /\.(png|jpe?g|gif|webp)$/i.test(name || '');
}
function previewUrl(item) {
  return typeof item.public_path === 'string' && /^\/f\/[A-Za-z0-9_-]{16,64}$/.test(item.public_path)
    ? appUrl(item.public_path.substring(1) + '?preview=1')
    : appUrl('api/preview/' + encodeURIComponent(item.code));
}
function openHistoryPreview(item) {
  const dialog = $('preview-dialog');
  $('preview-name').textContent = item.name;
  $('preview-image').src = previewUrl(item);
  if (!dialog.open) dialog.showModal();
}
$('close-preview').onclick = () => $('preview-dialog').close();
$('preview-dialog').addEventListener('click', event => {
  if (event.target === $('preview-dialog')) $('preview-dialog').close();
});
$('preview-dialog').addEventListener('close', () => $('preview-image').removeAttribute('src'));
$('preview-image').addEventListener('error', () => {
  $('preview-name').textContent = '图片预览失败，文件可能已经过期';
});
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
    if (item.has_file && isImageName(item.name) && !expired) {
      const preview = document.createElement('button');
      preview.type = 'button';
      preview.className = 'history-preview';
      preview.title = '点击预览图片';
      preview.setAttribute('aria-label', '预览 ' + item.name);
      const thumb = document.createElement('img');
      thumb.loading = 'lazy';
      thumb.alt = '';
      thumb.src = previewUrl(item);
      thumb.onerror = () => {
        thumb.remove();
        preview.textContent = '预览图片';
      };
      preview.append(thumb);
      preview.onclick = () => openHistoryPreview(item);
      row.append(preview);
    }
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
$('send-tip').textContent = '✦ 默认 3 天后自动销毁 · 无需登录';

function flash(message) {
  $('message').textContent = message || '';
}
let activePane = 'send';
function pane(name) {
  const tabNames = ['send', 'get', 'history'];
  const nextIndex = tabNames.indexOf(name);
  const currentIndex = tabNames.indexOf(activePane);
  if (nextIndex >= 0) {
    document.querySelector('.tabs').style.setProperty('--tab-index', String(nextIndex));
    document.querySelector('.workspace').dataset.slideDirection =
      nextIndex < currentIndex ? 'backward' : 'forward';
  }
  document.body.classList.toggle('is-done', name === 'done');
  ['send', 'get', 'history', 'done'].forEach(item => {
    $('pane-' + item).hidden = item !== name;
  });
  for (const tab of tabNames) {
    $('tab-' + tab).classList.toggle('active', name === tab);
    $('tab-' + tab).setAttribute('aria-selected', String(name === tab));
  }
  activePane = name;
  if (name === 'history') renderHistory();
  flash('');
}
// Slide the highlight, rather than abruptly recoloring each expiry option.
const ttlOptions = document.querySelector('.ttl-options');
const ttlInputs = [...document.querySelectorAll('input[name="ttl"]')];
function syncTtlSlider() {
  const index = Math.max(0, ttlInputs.findIndex(input => input.checked));
  ttlOptions.style.setProperty('--ttl-index', String(index));
}
ttlInputs.forEach(input => input.addEventListener('change', syncTtlSlider));
syncTtlSlider();
function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' 字节';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
  return (bytes / 1073741824).toFixed(2) + ' GB';
}
// Keep the popover rendered so opening and closing can animate smoothly.
// Inert prevents keyboard focus in visually closed menu items.
function setPickerOpen(open) {
  const menu = $('picker-menu');
  menu.dataset.state = open ? 'open' : 'closed';
  menu.inert = !open;
  menu.setAttribute('aria-hidden', String(!open));
  $('pick').setAttribute('aria-expanded', String(open));
  $('drop').classList.toggle('picker-expanded', open);
}
function closePicker() {
  setPickerOpen(false);
}
$('pick').onclick = () => setPickerOpen($('picker-menu').dataset.state !== 'open');
for (const [mode, input] of [['single', 'file'], ['multiple', 'files'], ['folder', 'folder']]) {
  $('pick-' + mode).onclick = () => {
    closePicker();
    $(input).click();
  };
  $(input).onchange = () => setFiles($(input).files, mode);
}
document.addEventListener('click', event => {
  if (!$('drop').contains(event.target)) closePicker();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') closePicker();
});
function setFiles(files, mode = 'single') {
  const items = Array.from(files || []);
  const total = items.reduce((sum, file) => sum + file.size, 0);
  if (items.length > 500 || total > MAX_FILE_BYTES || items.some(file => file.size > MAX_FILE_BYTES)) {
    selectedFiles = [];
    for (const id of ['file', 'files', 'folder']) $(id).value = '';
    flash(items.length > 500 ? '一次最多选择 500 个文件' : '单次总大小不能超过 5 GB');
  } else {
    selectedFiles = items;
    selectedMode = mode;
    if (items.length) flash('');
  }
  $('file-info').textContent = selectedFiles.length
    ? (mode === 'folder' ? '文件夹 · ' : '') +
      (selectedFiles.length === 1 ? selectedFiles[0].name : selectedFiles.length + ' 个文件') +
      ' · ' + formatSize(selectedFiles.reduce((sum, file) => sum + file.size, 0))
    : '';
  $('clear-file').hidden = !selectedFiles.length;
  $('selected-file').hidden = !selectedFiles.length;
}
$('clear-file').onclick = () => {
  for (const id of ['file', 'files', 'folder']) $(id).value = '';
  setFiles([], 'single');
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
  const files = Array.from(event.dataTransfer?.files || []);
  if (files.length) {
    closePicker();
    setFiles(files, files.length > 1 ? 'multiple' : 'single');
  }
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
  if (!selectedFiles.length && !text) { flash('请先选择文件，或输入一段文字。'); return; }
  if (selectedFiles.reduce((sum, file) => sum + file.size, 0) > MAX_FILE_BYTES) { flash('文件总大小不能超过 5 GB'); return; }
  const form = new FormData();
  form.append('ttl', document.querySelector('input[name="ttl"]:checked')?.value || '3d');
  form.append('selection', selectedMode);
  for (const file of selectedFiles) {
    form.append('file', file, selectedMode === 'folder' ? (file.webkitRelativePath || file.name) : file.name);
  }
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
async function writeClipboard(value) {
  if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch { /* Some mobile in-app browsers block Clipboard API. */ }
  }
  const temporary = document.createElement('textarea');
  temporary.value = value;
  temporary.readOnly = true;
  temporary.style.cssText = 'position:fixed;top:0;left:0;opacity:0;z-index:-1';
  document.body.append(temporary);
  temporary.focus();
  temporary.select();
  let copied = false;
  try { copied = document.execCommand('copy'); } catch { /* no clipboard permission */ }
  temporary.remove();
  return copied;
}
async function copyText(value, button, successLabel) {
  const copied = await writeClipboard(value);
  if (copied) {
    if (button) {
      const previous = button.textContent;
      button.textContent = successLabel;
      window.setTimeout(() => { button.textContent = previous; }, 1800);
    } else {
      flash('取件码已复制');
    }
  } else {
    flash('无法自动复制，请长按领取链接手动复制。');
  }
  return copied;
}
$('copy-code').onclick = () => copyText($('done-code').textContent, null, '');
$('copy-link').onclick = () => copyText(pickupUrl, $('copy-link'), '已复制');
$('copy-public-link').onclick = () => copyText($('copy-public-link').dataset.url, $('copy-public-link'), '已复制');

// Browsers cannot select a specific WeChat/QQ recipient without that app's
// cooperation. Always show an on-screen guide; offer native sharing where
// supported, and reliable copy/select as fallback in embedded browsers.
function shareVia(platform) {
  const target = platform === 'wechat' ? '微信' : 'QQ';
  const url = shareUrl || pickupUrl;
  if (!url) return;
  $('share-guide').hidden = false;
  $('share-guide-title').textContent = '分享到' + target;
  $('share-guide-tip').textContent = '点击“复制链接”，然后打开' + target + '粘贴给好友。';
  $('share-guide-url').value = url;
  $('share-system').hidden = typeof navigator.share !== 'function';
  $('share-wechat').setAttribute('aria-pressed', String(platform === 'wechat'));
  $('share-qq').setAttribute('aria-pressed', String(platform === 'qq'));
}
$('share-wechat').onclick = () => shareVia('wechat');
$('share-qq').onclick = () => shareVia('qq');
$('share-copy').onclick = async () => {
  const ok = await copyText($('share-guide-url').value, $('share-copy'), '已复制');
  if (ok) {
    $('share-guide-tip').textContent = '链接已复制！返回微信或 QQ 对话框粘贴发送即可。';
  } else {
    $('share-guide-tip').textContent = '请长按下方的链接选择“复制”，再发给好友。';
    $('share-guide-url').focus();
    $('share-guide-url').select();
  }
};
$('share-system').onclick = async () => {
  if (typeof navigator.share !== 'function') return;
  try {
    await navigator.share({ title: '好奇猴快传', text: '分享给你一个临时文件或文字', url: shareUrl || pickupUrl });
    $('share-guide-tip').textContent = '已打开手机分享选项。';
  } catch (error) {
    $('share-guide-tip').textContent = '未完成系统分享，请复制链接后在微信或 QQ 中发送。';
  }
};

$('again').onclick = () => {
  for (const id of ['file', 'files', 'folder']) $(id).value = '';
  $('text').value = '';
  setFiles([], 'single');
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
