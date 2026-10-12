'use strict';
// 好奇猴快传：原生网页交互，不依赖前端框架。
const $ = id => document.getElementById(id);
let selectedFile = null;
let pickupUrl = '';

const tokenParam = new URLSearchParams(location.hash.substring(1)).get('key');
if (tokenParam) {
  sessionStorage.setItem('hamoki_upload_key', tokenParam);
  history.replaceState(null, '', location.pathname + location.search);
}
const uploadKey = sessionStorage.getItem('hamoki_upload_key') || '';
$('send-tip').textContent = uploadKey
  ? '上传权限已激活 · 文件到期后自动删除'
  : '使用私密上传链接即可传送 · 领取无需登录';

function flash(message) {
  $('message').textContent = message || '';
}
function pane(name) {
  ['send', 'get', 'done'].forEach(item => {
    $('pane-' + item).hidden = item !== name;
  });
  $('tab-send').classList.toggle('active', name === 'send');
  $('tab-get').classList.toggle('active', name === 'get');
  $('tab-send').setAttribute('aria-selected', String(name === 'send'));
  $('tab-get').setAttribute('aria-selected', String(name === 'get'));
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
  if (selectedFile) $('text').value = '';
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
    $('drop').classList.add('drag');
  });
}
for (const name of ['dragleave', 'drop']) {
  $('drop').addEventListener(name, event => {
    event.preventDefault();
    $('drop').classList.remove('drag');
  });
}
$('drop').addEventListener('drop', event => {
  const file = event.dataTransfer?.files?.[0];
  if (file) setFile(file);
});
$('text').addEventListener('input', () => {
  if ($('text').value.trim() && selectedFile) {
    $('file').value = '';
    setFile(null);
  }
});
$('tab-send').onclick = () => pane('send');
$('tab-get').onclick = () => pane('get');

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
    request.open('POST', '/api/send');
    request.setRequestHeader('X-Upload-Key', uploadKey);
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
  if (!uploadKey) { flash('请使用私密上传链接打开网页。'); return; }
  if (!selectedFile && !text) { flash('请先选择文件，或输入一段文字。'); return; }
  const form = new FormData();
  form.append('ttl', $('ttl').value);
  if (selectedFile) form.append('file', selectedFile);
  else form.append('text', text);
  const button = $('upload');
  button.disabled = true;
  $('upload-progress').hidden = false;
  $('progress-bar').value = 0;
  $('upload-percent').textContent = '0%';
  flash('');
  try {
    const response = await sendForm(form);
    pickupUrl = location.origin + '/?code=' + encodeURIComponent(response.code);
    $('done-code').textContent = response.code;
    $('done-qr').src = '/api/qr/' + encodeURIComponent(response.code);
    $('copy-link').textContent = '复制领取链接';
    pane('done');
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
    const info = await readJson(await fetch('/api/item/' + encodeURIComponent(code)));
    $('found-name').textContent = info.name;
    $('found-details').textContent = info.kind === 'text'
      ? '文字内容 · 剩余 ' + info.remaining + ' 次领取'
      : formatSize(info.size) + ' · 剩余 ' + info.remaining + ' 次领取';
    $('claim').dataset.code = code;
    $('claim').dataset.kind = info.kind;
    $('claim').textContent = info.kind === 'text' ? '领取文字' : '下载文件';
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
  if ($('claim').dataset.kind === 'file') {
    location.href = '/d/' + encodeURIComponent(code);
    return;
  }
  try {
    const info = await readJson(await fetch('/api/text/' + encodeURIComponent(code), { method: 'POST' }));
    $('received-text').textContent = info.text;
    $('received-text').hidden = false;
    $('copy-text').hidden = false;
    flash('');
  } catch (error) {
    flash(error.message);
  }
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
