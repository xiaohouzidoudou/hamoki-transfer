'use strict';
const $=id=>document.getElementById(id);
let selectedFile=null, pickupUrl='';
const tokenParam=new URLSearchParams(location.hash.substring(1)).get('key');
if(tokenParam){sessionStorage.setItem('hamoki_upload_key',tokenParam);history.replaceState(null,'',location.pathname+location.search)}
const uploadKey=sessionStorage.getItem('hamoki_upload_key')||'';
$('send-tip').textContent=uploadKey?'上传权限已激活。文件到期自动删除。':'打开私密上传链接即可传文件，取件不需登录。';
function flash(t){$('message').textContent=t||''}
function pane(p){['send','get','done'].forEach(n=>$('pane-'+n).hidden=n!==p);$('tab-send').classList.toggle('active',p==='send');$('tab-get').classList.toggle('active',p==='get');flash('')}
function setFile(file){selectedFile=file;$('file-info').textContent=file?file.name+' ('+Math.round(file.size/1024)+' KB)':'';if(file)$('text').value=''}
$('pick').onclick=()=>$('file').click();$('file').onchange=()=>setFile($('file').files[0]||null);
for(const e of ['dragenter','dragover'])$('drop').addEventListener(e,ev=>{ev.preventDefault();$('drop').classList.add('drag')});
for(const e of ['dragleave','drop'])$('drop').addEventListener(e,ev=>{ev.preventDefault();$('drop').classList.remove('drag')});
$('drop').addEventListener('drop',ev=>setFile(ev.dataTransfer.files[0]||null));
$('tab-send').onclick=()=>pane('send');$('tab-get').onclick=()=>pane('get');
async function json(response){let body;try{body=await response.json()}catch{throw Error('服务器响应异常')}if(!response.ok)throw Error(body.error||'请求失败');return body}
$('upload').onclick=async()=>{
 const text=$('text').value.trim();if(!uploadKey){flash('请用私密上传链接打开本页。');return}if(!selectedFile&&!text){flash('请选择文件或粘贴文字。');return}
 const form=new FormData();form.append('ttl',$('ttl').value);if(selectedFile)form.append('file',selectedFile);else form.append('text',text);
 $('upload').disabled=true;flash('正在上传…');
 try{const response=await json(await fetch('/api/send',{method:'POST',headers:{'X-Upload-Key':uploadKey},body:form}));pickupUrl=location.origin+'/?code='+encodeURIComponent(response.code);$('done-code').textContent=response.code;$('done-qr').src='/api/qr/'+encodeURIComponent(response.code);pane('done')}
 catch(e){flash(e.message)}finally{$('upload').disabled=false}
};
$('copy-link').onclick=async()=>{try{await navigator.clipboard.writeText(pickupUrl);$('copy-link').textContent='已复制'}catch{flash('复制失败')}};
$('again').onclick=()=>{setFile(null);$('file').value='';$('text').value='';$('copy-link').textContent='复制取件链接';pane('send')};
$('lookup').onclick=async()=>{
 const code=$('code-input').value.trim().toUpperCase();if(!code){flash('请输入取件码');return}
 $('found').hidden=true;flash('正在查找…');
 try{const info=await json(await fetch('/api/item/'+encodeURIComponent(code)));$('found-name').textContent=info.name;$('found-details').textContent=info.kind==='text'?'文字内容':Math.round(info.size/1024)+' 千字节';$('claim').dataset.code=code;$('claim').dataset.kind=info.kind;$('claim').textContent=info.kind==='text'?'领取文字':'下载文件';$('received-text').hidden=true;$('copy-text').hidden=true;$('found').hidden=false;flash('')}
 catch(e){flash(e.message)}
};
$('claim').onclick=async()=>{
 const code=$('claim').dataset.code;if($('claim').dataset.kind==='file'){location.href='/d/'+encodeURIComponent(code);return}
 try{const info=await json(await fetch('/api/text/'+encodeURIComponent(code),{method:'POST'}));$('received-text').textContent=info.text;$('received-text').hidden=false;$('copy-text').hidden=false;flash('')}
 catch(e){flash(e.message)}
};
$('copy-text').onclick=async()=>{try{await navigator.clipboard.writeText($('received-text').textContent);$('copy-text').textContent='已复制'}catch{flash('复制失败')}};
$('code-input').addEventListener('keydown',e=>{if(e.key==='Enter')$('lookup').click()});
const incoming=new URLSearchParams(location.search).get('code');if(incoming){pane('get');$('code-input').value=incoming;$('lookup').click()}else pane('send');
