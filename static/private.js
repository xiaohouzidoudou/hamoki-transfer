'use strict';
(()=>{
const el=id=>document.getElementById(id);
const api=(path,opt={})=>fetch('api/private/'+path,{credentials:'same-origin',cache:'no-store',...opt});
const mutation=(path,payload)=>api(path,{method:'POST',headers:{'Content-Type':'application/json','X-Hamoki-Client':'1'},body:JSON.stringify(payload)});
const message=v=>{el('private-message').textContent=v||''};
let current='',paired=false,ready=false;
async function json(response){const val=await response.json().catch(()=>({error:'服务器返回异常'}));if(!response.ok)throw new Error(val.error||'操作失败');return val}
function privateActive(){return !el('private-workspace').hidden}
async function boot(){
 try{const status=await json(await api('me'));paired=status.paired;ready=true;
 el('private-onboard').hidden=paired;el('private-paired').hidden=!paired;
 if(paired)await refresh(true);
 }catch(e){message(e.message)}
}
async function refresh(force=false){
 if(!paired||(!privateActive()&&!force))return;
 try{const data=await json(await api('latest'));if(!force&&data.revision===current)return;
 current=data.revision;
 el('private-source').textContent=data.updated?(data.self_sent?'本设备':'来自 '+data.sender)+' · '+new Date(data.updated*1000).toLocaleString('zh-CN'):'等待发送';
 el('private-inbox').textContent=data.has_text?data.text:data.has_file?'已收到文件，点击下面下载':'还没有内容，在另一台设备发送后会自动显示。';
 el('private-copy').hidden=!data.has_text;
 el('private-file-row').hidden=!data.has_file;
 if(data.has_file)el('private-filename').textContent=data.filename+' · '+(data.size/1024/1024).toFixed(2)+' MB';
 }catch(e){if(!ready)return;message(e.message)}
}
el('private-create').onclick=async()=>{try{const data=await json(await mutation('create',{label:'我的设备'}));paired=true;await boot();window.prompt('保存此唯一配对码，用另一台设备输入一次。配对码请勿分享给他人：',data.invite);message('私人空间创建成功。请保存弹出的配对码。')}catch(e){message(e.message)}};
el('private-join').onclick=async()=>{try{await json(await mutation('join',{invite:el('private-invite-input').value.trim(),label:'我的设备'}));await boot();message('设备已绑定成功')}catch(e){message(e.message)}};
el('private-copy').onclick=async()=>{try{await navigator.clipboard.writeText(el('private-inbox').textContent);message('内容已复制')}catch{message('无法自动复制，请长按内容手动复制')}};
el('private-files').onchange=()=>{const a=Array.from(el('private-files').files);el('private-file-info').textContent=a.length?a.map(f=>f.name).join('、'):''};
el('private-send').onclick=async()=>{
 const text=el('private-text').value.trim(),files=Array.from(el('private-files').files);
 if(!text&&!files.length)return message('请输入文字或选择文件');
 const body=new FormData();body.append('text',text);for(const f of files)body.append('file',f,f.name);
 const btn=el('private-send');btn.disabled=true;el('private-progress').hidden=false;
 try{await json(await api('send',{method:'POST',headers:{'X-Hamoki-Client':'1'},body}));
 el('private-text').value='';el('private-files').value='';el('private-file-info').textContent='';
 await refresh(true);message('发送成功，其他设备打开网页即可接收');
 }catch(e){message(e.message)}finally{btn.disabled=false;el('private-progress').hidden=true}
};
el('private-settings-toggle').onclick=async()=>{
 el('private-settings').hidden=false;
 try{await loadInvite();const d=await json(await api('devices'));el('private-device-list').replaceChildren();
 for(const row of d.devices){const line=document.createElement('div');line.className='private-device';
 const label=document.createElement('span');label.textContent=row.label+(row.me?'（本机）':'');line.append(label);
 if(!row.me){const btn=document.createElement('button');btn.className='secondary';btn.textContent='解绑';btn.onclick=()=>revoke(row.id);line.append(btn)}
 el('private-device-list').append(line)}}catch(e){message(e.message)}
};
async function loadInvite(){
 const data=await json(await api('invite'));
 if(data.available){
  el('private-invite-display').textContent=data.invite;
  el('private-invite-copy').hidden=false;
  el('private-invite-show').hidden=true;
  el('private-invite-notice').textContent='只有配对过的设备才能查看。';
 }else{
  el('private-invite-notice').textContent='旧版配对码只保存了校验值，无法恢复原文。点击下方按钮生成新的长期配对码；已绑定设备不会退出。';
  el('private-invite-show').textContent='生成新配对码';
  el('private-invite-show').hidden=false;
 }
}
el('private-invite-show').onclick=async()=>{
 try{
  const data=await json(await api('invite'));
  if(!data.available){
   if(!confirm('旧配对码将失效，但已有设备保持绑定。确定生成新配对码吗？'))return;
   const updated=await json(await mutation('invite/reissue',{}));
   el('private-invite-display').textContent=updated.invite;
   el('private-invite-copy').hidden=false;
   el('private-invite-show').hidden=true;
   el('private-invite-notice').textContent='新配对码已生效，原配对码失效。';
  }else await loadInvite();
 }catch(e){message(e.message)}
};
el('private-invite-copy').onclick=async()=>{
 try{await navigator.clipboard.writeText(el('private-invite-display').textContent);message('配对码已复制')}
 catch{message('复制失败，请手动选中配对码')}
};
el('private-settings-close').onclick=()=>el('private-settings').hidden=true;
async function revoke(id){if(!confirm('确定解除这个设备的绑定？'))return;try{await json(await mutation('revoke',{device_id:id}));await boot();el('private-settings-toggle').click()}catch(e){message(e.message)}}
el('private-leave').onclick=()=>{if(confirm('解除本机绑定？你需要用原配对码重新加入。'))revokeOwn()};
async function revokeOwn(){try{const d=await json(await api('me'));await json(await mutation('revoke',{device_id:d.device_id}));paired=false;current='';await boot();message('本机已解除绑定')}catch(e){message(e.message)}}
window.hamokiPrivateOpen=()=>{refresh(true)};
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});
setInterval(()=>{if(!document.hidden)refresh()},6000);
boot();
})();