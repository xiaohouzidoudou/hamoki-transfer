'use strict';
(()=>{
const el=id=>document.getElementById(id);
const api=(path,opt={})=>fetch('api/private/'+path,{credentials:'same-origin',cache:'no-store',...opt});
const mutation=(path,payload)=>api(path,{method:'POST',headers:{'Content-Type':'application/json','X-Hamoki-Client':'1'},body:JSON.stringify(payload)});
const message=v=>{el('private-message').textContent=v||''};
let current='',paired=false,ready=false;
let chosenFiles=[];
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
el('private-create').onclick=async()=>{try{await json(await mutation('create',{label:'我的设备'}));paired=true;await boot();await openSettings();message('创建成功，配对码已在设备管理中显示。')}catch(e){message(e.message)}};
el('private-join').onclick=async()=>{try{await json(await mutation('join',{invite:el('private-invite-input').value.trim(),label:'我的设备'}));await boot();message('设备已绑定成功')}catch(e){message(e.message)}};
el('private-copy').onclick=async()=>{try{await navigator.clipboard.writeText(el('private-inbox').textContent);message('内容已复制')}catch{message('无法自动复制，请长按内容手动复制')}};
function renderChosenFiles(){
 const list=el('private-selected-list');list.replaceChildren();
 el('private-file-selection').hidden=!chosenFiles.length;
 for(const [index,file] of chosenFiles.entries()){
  const row=document.createElement('div');row.className='private-selected-item';
  const name=document.createElement('span');name.textContent=file.name;
  const remove=document.createElement('button');remove.type='button';remove.className='private-remove';remove.textContent='移除';
  remove.onclick=()=>{chosenFiles.splice(index,1);el('private-files').value='';renderChosenFiles()};
  row.append(name,remove);list.append(row);
 }
 el('private-file-info').textContent=chosenFiles.length?'共 '+chosenFiles.length+' 个文件':'';
}
el('private-files').onchange=()=>{chosenFiles=Array.from(el('private-files').files);renderChosenFiles()};
el('private-files-clear').onclick=()=>{chosenFiles=[];el('private-files').value='';renderChosenFiles()};

const privateDropZone=el('private-send-zone');
let fileDragDepth=0;
function hasDraggedFiles(event){
 return Array.from(event.dataTransfer?.types||[]).includes('Files');
}
function clearDragHighlight(){
 fileDragDepth=0;
 privateDropZone.classList.remove('is-dragging');
}
privateDropZone.addEventListener('dragenter',event=>{
 if(!hasDraggedFiles(event))return;
 event.preventDefault();
 fileDragDepth++;
 privateDropZone.classList.add('is-dragging');
});
privateDropZone.addEventListener('dragover',event=>{
 if(!hasDraggedFiles(event))return;
 event.preventDefault();
 event.dataTransfer.dropEffect='copy';
 privateDropZone.classList.add('is-dragging');
});
privateDropZone.addEventListener('dragleave',event=>{
 if(!hasDraggedFiles(event))return;
 fileDragDepth=Math.max(0,fileDragDepth-1);
 if(!fileDragDepth)privateDropZone.classList.remove('is-dragging');
});
privateDropZone.addEventListener('drop',event=>{
 if(!hasDraggedFiles(event))return;
 event.preventDefault();
 clearDragHighlight();
 const incoming=Array.from(event.dataTransfer?.files||[]);
 if(!incoming.length)return message('请拖动文件或图片到发送区域');
 const names=new Set(chosenFiles.map(file=>file.name));
 const added=incoming.filter(file=>!names.has(file.name)&&!!names.add(file.name));
 if(!added.length)return message('这些文件已添加，无需重复选择');
 const totalFiles=chosenFiles.concat(added);
 if(totalFiles.length>500)return message('一次最多上传500个文件');
 if(totalFiles.reduce((sum,file)=>sum+file.size,0)>5*1024*1024*1024)return message('文件总大小不能超过5 GB');
 chosenFiles=totalFiles;
 // The actual file objects stay in chosenFiles even if the input is cleared.
 el('private-files').value='';
 renderChosenFiles();
 message('已添加'+added.length+'个文件，点击发送即可上传');
});
// Prevent accidentally leaving the transfer site if the drop misses the box.
document.addEventListener('dragover',event=>{
 if(hasDraggedFiles(event))event.preventDefault();
});
document.addEventListener('drop',event=>{
 if(hasDraggedFiles(event)){
  event.preventDefault();
  clearDragHighlight();
 }
});
window.addEventListener('blur',clearDragHighlight);


el('private-send').onclick=async()=>{
 const text=el('private-text').value.trim(),files=chosenFiles.slice();
 if(!text&&!files.length)return message('请输入文字或选择文件');
 const body=new FormData();body.append('text',text);for(const f of files)body.append('file',f,f.name);
 const btn=el('private-send');btn.disabled=true;el('private-progress').hidden=false;
 try{await json(await api('send',{method:'POST',headers:{'X-Hamoki-Client':'1'},body}));
 el('private-text').value='';el('private-files').value='';chosenFiles=[];renderChosenFiles();
 await refresh(true);message('发送成功，其他设备打开网页即可接收');
 }catch(e){message(e.message)}finally{btn.disabled=false;el('private-progress').hidden=true}
};
async function showDevices(){
 const d=await json(await api('devices'));const list=el('private-device-list');list.replaceChildren();
 for(const row of d.devices){
  const line=document.createElement('div');line.className='private-device';
  const label=document.createElement('span');label.textContent=row.label+(row.me?'（本机）':'');
  const actions=document.createElement('div');actions.className='private-device-actions';
  const rename=document.createElement('button');rename.type='button';rename.className='secondary';rename.textContent='改名';
  rename.onclick=async()=>{
   const wanted=prompt('给设备起个容易辨认的名字（最多24个字）',row.label);
   if(wanted===null)return;
   try{await json(await mutation('rename',{device_id:row.id,name:wanted.trim()}));message('设备名称已更新');await showDevices();await refresh(true)}
   catch(e){message(e.message)}
  };
  actions.append(rename);
  if(!row.me){
   const revokeButton=document.createElement('button');revokeButton.type='button';revokeButton.className='private-danger';revokeButton.textContent='解绑';
   revokeButton.onclick=()=>revoke(row.id);actions.append(revokeButton);
  }
  line.append(label,actions);list.append(line);
 }
}
let inviteLoading=false;
async function loadInviteInline(){
 if(inviteLoading)return;
 inviteLoading=true;
 const display=el('private-invite-display'),copy=el('private-invite-copy'),notice=el('private-invite-notice');
 display.textContent='正在读取配对码…';
 copy.hidden=true;
 notice.textContent='';
 try{
  let data=await json(await api('invite'));
  if(!data.available){
   // Pre-upgrade rooms only stored an irreversible hash. Reissue silently
   // and keep all current device credentials and private content intact.
   data=await json(await mutation('invite/reissue',{}));
   notice.textContent='旧配对码已自动更新，原来绑定的设备仍可正常使用。';
  }else{
   notice.textContent='仅已绑定设备可查看，请妥善保管。';
  }
  if(!data.available||typeof data.invite!=='string')throw Error('服务器没有返回有效配对码');
  display.textContent=data.invite;
  copy.hidden=false;
 }catch(e){
  display.textContent='配对码读取失败';
  notice.textContent='请稍后重新进入设备管理：'+e.message;
 }finally{inviteLoading=false}
}
async function openSettings(){
 el('private-settings').hidden=false;
 // Render code and device list independently so one failure cannot hide the other.
 await Promise.allSettled([loadInviteInline(),showDevices().catch(e=>message('设备列表读取失败：'+e.message))]);
}
el('private-settings-toggle').onclick=openSettings;
el('private-invite-copy').onclick=async()=>{
 const code=el('private-invite-display').textContent;
 try{await navigator.clipboard.writeText(code);message('配对码已复制')}
 catch{message('复制失败，请长按配对码手动复制')}
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