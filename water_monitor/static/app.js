const fields = [['temperature_c','Temperature','°C'],['ph','pH',''],['dissolved_oxygen_mg_l','Dissolved oxygen','mg/L'],['turbidity_ntu','Turbidity','NTU']];
for (const [key,label,unit] of fields) {
  const card=document.createElement('article');
  const title=document.createElement('h2'); title.textContent=label;
  const value=document.createElement('strong'); value.id=key; value.textContent='—';
  const suffix=document.createElement('span'); suffix.textContent=unit;
  card.append(title,value,suffix); document.querySelector('#readings').append(card);
}
async function request(path,method='GET') {
  const response=await fetch(path,{method,headers:method==='POST'?{'X-Monitor-Request':'1'}:{},signal:AbortSignal.timeout(5000)});
  const data=await response.json(); if(!response.ok) throw new Error(data.error); return data;
}
async function sessions() {
  const items=await request('/api/sessions');
  const active=items.some(item=>item.ended===null);
  document.querySelector('#start').disabled=active;
  document.querySelector('#stop').disabled=!active;
  const list=document.querySelector('#sessions'); list.replaceChildren();
  for(const item of items) {
    const row=document.createElement('li'); row.textContent=`Survey ${item.id} · ${new Date(item.started).toLocaleString()} · ${item.ended?'Saved':'Recording'} `;
    const link=document.createElement('a'); link.href=`/api/export/${item.id}`; link.download=`survey-${item.id}.csv`; link.textContent='Download CSV'; row.append(link); list.append(row);
  }
}
for(const action of ['start','stop']) document.querySelector(`#${action}`).addEventListener('click',async()=>{
  try {const result=await request(`/api/sessions/${action}`,'POST');document.querySelector('#message').textContent=`Survey ${result.session_id}: ${action}`;await sessions();}
  catch(error){document.querySelector('#message').textContent=error.message;}
});
async function refresh(){
  try {const data=await request('/api/telemetry');for(const [key] of fields)document.getElementById(key).textContent=data[key].toFixed(2);
    document.querySelector('#status').textContent=`Connected · ${new Date(data.timestamp).toLocaleTimeString()}`;
    document.querySelector('#position').textContent=`Fixed simulated station: ${data.latitude}, ${data.longitude}`;await sessions();
  }catch(error){document.querySelector('#status').textContent='Disconnected · Displayed readings may be stale';}
  setTimeout(refresh,1000);
}
refresh();
