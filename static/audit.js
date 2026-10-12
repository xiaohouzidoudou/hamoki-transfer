'use strict';
(()=>{
const get=id=>document.getElementById(id);
const message=text=>{get('audit-message').textContent=text||''};
const api=(path,opt={})=>fetch('/api/admin/'+path,{cache:'no-store',credentials:'same-origin',...opt});
async function read(response){
 const body=await response.json().catch(()=>({error:'服务器响应异常'}));
 if(!response.ok)throw Error(body.error||'请求失败');
 return body;
}
let offset=0,bounds=null;
function selectedDay(){
 const date=get('audit-date').value;
 const d=new Date(date+'T00:00:00');
 if(!date||Number.isNaN(d.getTime()))throw Error('请选择日期');
 return {from:Math.floor(d.getTime()/1000),to:Math.floor(new Date(d.getFullYear(),d.getMonth(),d.getDate()+1).getTime()/1000)};
}
function showLogin(loggedIn){
 get('audit-login-form').hidden=loggedIn;
 get('audit-data').hidden=!loggedIn;
}
function fmt(ts){return new Date(ts*1000).toLocaleTimeString('zh-CN',{hour12:false})}
function row(event){
 const tr=document.createElement('tr');
 const time=document.createElement('td');time.textContent=fmt(event.created);
 const client=document.createElement('td');client.textContent=event.ip;
 if(event.device){const label=document.createElement('small');label.textContent=event.device;client.append(label)}
 const what=document.createElement('td');what.textContent=event.action;
 const status=document.createElement('td');status.textContent=String(event.status);
 status.className=event.status>=400?'audit-status-warn':'audit-status-good';
 tr.append(time,client,what,status);return tr;
}
async function loadSummary(){
 const query=new URLSearchParams(bounds).toString();
 const d=await read(await api('summary?'+query));
 get('audit-requests').textContent=d.totals.requests||0;
 get('audit-ips').textContent=d.totals.ips||0;
 get('audit-uploads').textContent=d.totals.uploads||0;
 get('audit-failures').textContent=d.totals.failures||0;
}
async function loadEvents(append){
 const query=new URLSearchParams({...bounds,offset:offset}).toString();
 const d=await read(await api('events?'+query));
 if(!append)get('audit-rows').replaceChildren();
 for(const event of d.events)get('audit-rows').append(row(event));
 offset+=d.events.length;
 get('audit-count').textContent='共 '+d.total+' 条';
 get('audit-more').hidden=offset>=d.total;
 if(!offset){
   const tr=document.createElement('tr'),cell=document.createElement('td');
   cell.colSpan=4;cell.textContent='当天暂无访问记录';tr.append(cell);get('audit-rows').append(tr);
 }
}
async function refresh(){
 bounds=selectedDay();offset=0;message('正在读取…');
 try{await Promise.all([loadSummary(),loadEvents(false)]);message('')}
 catch(e){if(e.message.includes('登录'))showLogin(false);message(e.message)}
}
get('audit-login-form').onsubmit=async event=>{
 event.preventDefault();
 const pass=get('audit-password').value;
 try{
   await read(await api('login',{method:'POST',headers:{'Content-Type':'application/json','X-Hamoki-Client':'1'},body:JSON.stringify({password:pass})}));
   get('audit-password').value='';showLogin(true);await refresh();
 }catch(e){message(e.message)}
};
get('audit-refresh').onclick=refresh;
get('audit-date').onchange=refresh;
get('audit-more').onclick=async()=>{
 try{await loadEvents(true)}catch(e){message(e.message)}
};
get('audit-logout').onclick=async()=>{
 try{await read(await api('logout',{method:'POST',headers:{'X-Hamoki-Client':'1'}}))}
 catch(e){message(e.message)}
 showLogin(false);get('audit-rows').replaceChildren();offset=0;
};
const today=new Date();get('audit-date').value=[today.getFullYear(),String(today.getMonth()+1).padStart(2,'0'),String(today.getDate()).padStart(2,'0')].join('-');
get('audit-date').max=get('audit-date').value;
read(api('session')).then(state=>{showLogin(state.authenticated);if(state.authenticated)refresh()}).catch(e=>message(e.message));
})();
