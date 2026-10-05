let plannerSignature = '';
let plannerVersion = 0;

function replaceOptions(select, options, placeholder) {
  const selected = select.value;
  select.replaceChildren();
  const empty = element('option', placeholder); empty.value = ''; select.append(empty);
  for (const [value, label] of options) {const option = element('option', label); option.value = value; select.append(option);}
  if (options.some(([value]) => value === selected)) select.value = selected;
}
function locationOverview(locations) {
  const panel = document.querySelector('#location-map'); panel.replaceChildren();
  panel.append(element('h3', 'Location coordinate overview (schematic)'));
  if (!locations.length) {panel.append(element('p', 'No locations saved yet.')); return;}
  const latitudes = locations.map(site => site.latitude), longitudes = locations.map(site => site.longitude);
  const latitudeMin = Math.min(...latitudes), latitudeMax = Math.max(...latitudes);
  const longitudeMin = Math.min(...longitudes), longitudeMax = Math.max(...longitudes);
  const latitudePad = Math.max((latitudeMax - latitudeMin) * 0.15, 0.01);
  const longitudePad = Math.max((longitudeMax - longitudeMin) * 0.15, 0.01);
  const bottom = latitudeMin - latitudePad, top = latitudeMax + latitudePad;
  const left = longitudeMin - longitudePad, right = longitudeMax + longitudePad;
  const x = longitude => 75 + (longitude - left) / (right - left) * 495;
  const y = latitude => 250 - (latitude - bottom) / (top - bottom) * 210;
  const svg = svgElement('svg', {viewBox:'0 0 620 320',role:'img','aria-label':'Saved sampling locations plotted by longitude and latitude. Markers are numbered by location ID; full coordinates appear in the list below.'});
  for (let step = 0; step <= 4; step++) {
    const latitude = bottom + (top - bottom) * step / 4;
    svg.append(svgElement('line',{x1:75,x2:570,y1:y(latitude),y2:y(latitude),class:'gridline'}));
    svg.append(svgElement('text',{x:70,y:y(latitude)+4,'text-anchor':'end'},latitude.toFixed(3)));
    const longitude = left + (right - left) * step / 4;
    svg.append(svgElement('line',{x1:x(longitude),x2:x(longitude),y1:40,y2:250,class:'gridline'}));
    svg.append(svgElement('text',{x:x(longitude),y:273,'text-anchor':'middle'},longitude.toFixed(3)));
  }
  for (const site of locations) {
    const marker = svgElement('circle',{cx:x(site.longitude),cy:y(site.latitude),r:5,class:'trend-dot'});
    marker.append(svgElement('title',{},`${site.name}: ${site.latitude}, ${site.longitude}`)); svg.append(marker);
    svg.append(svgElement('text',{x:x(site.longitude)+9,y:y(site.latitude)-9},`#${site.id}`));
  }
  svg.append(svgElement('text',{x:320,y:309,'text-anchor':'middle'},'Longitude (degrees) · latitude increases upward'));
  panel.append(svg,element('p','Offline coordinate plot with an automatic scale. It has no shoreline basemap; nearby or identical locations may overlap.'));
}
function renderPlanner(locations, plans) {
  const signature = JSON.stringify([locations, plans, plans.map(plan => plan.status === 'planned' && Date.parse(plan.scheduled_for) < Date.now())]);
  if (signature === plannerSignature) return;
  plannerSignature = signature;
  replaceOptions(document.querySelector('#plan-location'), locations.map(site => [String(site.id),site.name]), 'Choose a location');
  const labels = locations.map(site => [`location:${site.id}`,`Location: ${site.name}`]);
  for (const plan of plans.filter(item => ['planned','interrupted','recording'].includes(item.status))) labels.push([`plan:${plan.id}`,`Plan ${plan.id}: ${plan.location_name} · ${new Date(plan.scheduled_for).toLocaleString()} (${plan.status})`]);
  replaceOptions(document.querySelector('#record-label'), labels, 'Unassigned synthetic survey');
  locationOverview(locations);
  const list = document.querySelector('#location-list'); list.replaceChildren();
  for (const site of locations) list.append(element('li',`#${site.id} ${site.name} · ${site.latitude}, ${site.longitude}${site.notes ? ` · ${site.notes}` : ''}`));
  const schedule = document.querySelector('#plan-list'); schedule.replaceChildren();
  if (!plans.length) schedule.append(element('li','No observations scheduled yet.'));
  for (const plan of plans) {
    const overdue = plan.status === 'planned' && Date.parse(plan.scheduled_for) < Date.now() ? ' · scheduled time has passed' : '';
    const row = element('li',`Plan ${plan.id}: ${plan.location_name} · ${new Date(plan.scheduled_for).toLocaleString()} · ${plan.status}${overdue}${plan.notes ? ` · ${plan.notes}` : ''} `);
    if (['planned','interrupted'].includes(plan.status)) {
      const cancel = element('button','Cancel plan');
      cancel.addEventListener('click',async()=>{try{await request('/api/plans/cancel','POST',{plan_id:plan.id}); await plannerRefresh();}catch(error){document.querySelector('#planner-message').textContent=error.message;}});
      row.append(cancel);
    }
    schedule.append(row);
  }
}
function renderComparison(rows) {
  const panel = document.querySelector('#comparison');
  const previousScroll = panel.querySelector('.table-scroll')?.scrollLeft || 0;
  panel.replaceChildren();
  panel.append(element('h3','Synthetic readings by planning label'));
  panel.append(element('p','Means combine all samples tagged with each location, including different simulation profiles. They are not physical measurements at those locations.'));
  if (!rows.length) return;
  const wrapper = element('div'); wrapper.className='table-scroll';
  const table = element('table'); const heading = element('tr');
  for (const label of ['Location','Surveys','Samples',...fields.map(([,label,unit])=>`${label} ${unit}`)]) heading.append(element('th',label));
  table.append(heading);
  for (const row of rows) {
    const cells = [row.location_name,row.session_count,row.sample_count,...fields.map(([key])=>row.means[key] === null ? '—' : row.means[key])];
    const tr = element('tr'); for (const cell of cells) tr.append(element('td',String(cell))); table.append(tr);
  }
  wrapper.append(table); panel.append(wrapper); wrapper.scrollLeft = previousScroll;
}
async function plannerRefresh() {
  const version = ++plannerVersion;
  try {
    const [locations,plans,comparison] = await Promise.all([request('/api/locations'),request('/api/plans'),request('/api/comparison')]);
    if (version !== plannerVersion) return;
    renderPlanner(locations,plans); renderComparison(comparison);
  } catch(error) {document.querySelector('#planner-message').textContent=`Planner unavailable: ${error.message}`;}
}
document.querySelector('#location-form').addEventListener('submit',async event=>{
  event.preventDefault();
  try {
    await request('/api/locations','POST',{name:document.querySelector('#location-name').value,latitude:Number(document.querySelector('#location-latitude').value),longitude:Number(document.querySelector('#location-longitude').value),notes:document.querySelector('#location-notes').value});
    document.querySelector('#location-form').reset(); document.querySelector('#planner-message').textContent='Location saved.'; await plannerRefresh();
  }catch(error){document.querySelector('#planner-message').textContent=error.message;}
});
document.querySelector('#plan-form').addEventListener('submit',async event=>{
  event.preventDefault();
  try {
    await request('/api/plans','POST',{location_id:Number(document.querySelector('#plan-location').value),scheduled_for:new Date(document.querySelector('#plan-time').value).toISOString(),notes:document.querySelector('#plan-notes').value});
    document.querySelector('#plan-form').reset(); document.querySelector('#planner-message').textContent='Observation plan saved. Start recording manually when ready.'; await plannerRefresh();
  }catch(error){document.querySelector('#planner-message').textContent=error.message;}
});
async function plannerPoll(){await plannerRefresh();setTimeout(plannerPoll,3000);}
plannerPoll();
