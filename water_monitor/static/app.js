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
    const link=document.createElement('a'); link.href=`/api/export/${item.id}`; link.download=`survey-${item.id}.csv`; link.textContent='Download CSV'; row.append(link); const summary=document.createElement('button'); summary.textContent='View summary'; summary.addEventListener('click',()=>showSummary(item.id)); row.append(summary); list.append(row);
  }
}
for(const action of ['start','stop']) document.querySelector(`#${action}`).addEventListener('click',async()=>{
  try {const result=await request(`/api/sessions/${action}`,'POST');document.querySelector('#message').textContent=`Survey ${result.session_id}: ${action}`;await sessions();}
  catch(error){document.querySelector('#message').textContent=error.message;}
});
async function refresh(){
  try {const data=await request('/api/telemetry');for(const [key] of fields)document.getElementById(key).textContent=data[key].toFixed(2);
    const health=await request('/api/health'); document.querySelector('#status').textContent=`Connected · ${health.profile} · ${health.sample_interval_seconds}s interval · ${new Date(data.timestamp).toLocaleTimeString()}`;
    document.querySelector('#position').textContent=`Fixed simulated station: ${data.latitude}, ${data.longitude}`;await sessions();
  }catch(error){document.querySelector('#status').textContent='Disconnected · Displayed readings may be stale';}
  setTimeout(refresh,1000);
}
refresh();

async function showSummary(sessionId) {
  try {
    const data = await request(`/api/summary/${sessionId}`);
    const panel = document.querySelector('#summary');
    panel.replaceChildren();
    const title = document.createElement('h3');
    title.textContent = `Survey ${data.session_id} · ${data.sample_count} samples · ${data.profiles.join(', ') || 'No samples yet'}`;
    panel.append(title);
    const table = document.createElement('table');
    const header = document.createElement('tr');
    for (const text of ['Sensor', 'Minimum', 'Mean', 'Maximum']) {
      const cell = document.createElement('th'); cell.textContent = text; header.append(cell);
    }
    table.append(header);
    for (const [key, label, unit] of fields) {
      const row = document.createElement('tr');
      for (const value of [`${label} ${unit}`, data.metrics[key].min, data.metrics[key].mean, data.metrics[key].max]) {
        const cell = document.createElement('td'); cell.textContent = value === null ? '—' : String(value); row.append(cell);
      }
      table.append(row);
    }
    panel.append(table);
  } catch (error) { document.querySelector('#message').textContent = error.message; }
}
