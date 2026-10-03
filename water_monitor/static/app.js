const fields = [
  ['temperature_c', 'Temperature', '°C'],
  ['ph', 'pH', ''],
  ['dissolved_oxygen_mg_l', 'Dissolved oxygen', 'mg/L'],
  ['turbidity_ntu', 'Turbidity', 'NTU'],
];
let selectedSurvey = null;
let surveyRequest = 0;
let sessionSignature = '';

function element(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}
for (const [key, label, unit] of fields) {
  const card = element('article');
  const value = element('strong', '—'); value.id = key;
  card.append(element('h2', label), value, element('span', unit));
  document.querySelector('#readings').append(card);
}
async function request(path, method = 'GET') {
  const response = await fetch(path, {
    method,
    headers: method === 'POST' ? {'X-Monitor-Request': '1'} : {},
    signal: AbortSignal.timeout(5000),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || data.status || 'Request failed');
  return data;
}
async function sessions() {
  const items = await request('/api/sessions');
  const active = items.some(item => item.ended === null);
  document.querySelector('#start').disabled = active;
  document.querySelector('#stop').disabled = !active;
  const signature = JSON.stringify(items);
  // Keep existing buttons and keyboard focus while the session list is unchanged.
  if (signature === sessionSignature) return;
  sessionSignature = signature;
  const list = document.querySelector('#sessions'); list.replaceChildren();
  for (const item of items) {
    const row = element('li', `Survey ${item.id} · ${new Date(item.started).toLocaleString()} · ${item.ended ? 'Saved' : 'Recording'} `);
    for (const format of ['csv', 'json']) {
      const link = element('a', `Download ${format.toUpperCase()}`);
      link.href = `/api/export/${item.id}?format=${format}`;
      link.download = `survey-${item.id}.${format}`;
      row.append(link, document.createTextNode(' '));
    }
    const button = element('button', 'View survey');
    button.addEventListener('click', () => {
      selectedSurvey = item.id;
      updateSurvey();
    });
    row.append(button); list.append(row);
  }
}
for (const action of ['start', 'stop']) {
  document.querySelector(`#${action}`).addEventListener('click', async () => {
    try {
      const result = await request(`/api/sessions/${action}`, 'POST');
      document.querySelector('#message').textContent = `Survey ${result.session_id}: ${action}`;
      selectedSurvey = result.session_id;
      await sessions();
      await updateSurvey();
    } catch (error) { document.querySelector('#message').textContent = error.message; }
  });
}
function renderSummary(data) {
  const panel = document.querySelector('#summary'); panel.replaceChildren();
  panel.append(element('h3', `Survey ${data.session_id} · ${data.sample_count} samples · ${data.profiles.join(', ') || 'No samples yet'}`));
  const table = element('table');
  const header = element('tr');
  for (const text of ['Sensor', 'Minimum', 'Mean', 'Maximum']) header.append(element('th', text));
  table.append(header);
  for (const [key, label, unit] of fields) {
    const row = element('tr');
    for (const value of [`${label} ${unit}`, data.metrics[key].min, data.metrics[key].mean, data.metrics[key].max]) {
      row.append(element('td', value === null ? '—' : String(value)));
    }
    table.append(row);
  }
  panel.append(table);
}
function svgElement(tag, attributes, text) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}
function renderTrends(data) {
  const panel = document.querySelector('#trends'); panel.replaceChildren();
  panel.append(element('h3', `Recent trends · last ${data.samples.length} recorded samples (maximum ${data.limit})`));
  if (!data.samples.length) {
    panel.append(element('p', 'No recorded samples yet. Start recording and wait for the next sample.'));
    return;
  }
  const grid = element('div'); grid.className = 'trend-grid';
  for (const [key, label, unit] of fields) {
    const values = data.samples.map(sample => Number(sample[key]));
    const times = data.samples.map(sample => Date.parse(sample.timestamp));
    const low = Math.min(...values), high = Math.max(...values);
    const padding = Math.max((high - low) * 0.1, 0.1);
    const min = low - padding, max = high + padding;
    const start = times[0], end = times[times.length - 1];
    const x = time => end === start ? 330 : 70 + (time - start) / (end - start) * 510;
    const y = value => 160 - (value - min) / (max - min) * 130;
    const card = element('article'); card.append(element('h4', `${label} ${unit}`));
    const svg = svgElement('svg', {viewBox: '0 0 620 220', role: 'img', 'aria-label': `${label}: ${low.toFixed(2)} to ${high.toFixed(2)} ${unit}. ${data.samples.length} samples. Time runs left to right.`});
    for (const value of [min, (min + max) / 2, max]) {
      svg.append(svgElement('line', {x1: 70, x2: 580, y1: y(value), y2: y(value), class: 'gridline'}));
      svg.append(svgElement('text', {x: 62, y: y(value) + 4, 'text-anchor': 'end'}, value.toFixed(2)));
    }
    const points = values.map((value, index) => `${x(times[index])},${y(value)}`).join(' ');
    svg.append(svgElement('polyline', {points, class: 'trend-line'}));
    if (values.length === 1) svg.append(svgElement('circle', {cx: x(start), cy: y(values[0]), r: 4, class: 'trend-dot'}));
    svg.append(svgElement('text', {x: 70, y: 190}, new Date(start).toLocaleTimeString()));
    svg.append(svgElement('text', {x: 580, y: 190, 'text-anchor': 'end'}, new Date(end).toLocaleTimeString()));
    svg.append(svgElement('text', {x: 330, y: 214, 'text-anchor': 'middle'}, 'Sample time · automatic vertical scale'));
    card.append(svg); grid.append(card);
  }
  panel.append(grid, element('p', 'Synthetic data. Chart scales adjust to the selected samples; these are not water-safety limits.'));
}
async function updateSurvey() {
  if (selectedSurvey === null) return;
  const id = selectedSurvey, token = ++surveyRequest;
  try {
    const [summary, series] = await Promise.all([
      request(`/api/summary/${id}`), request(`/api/series/${id}?limit=120`),
    ]);
    if (token !== surveyRequest || id !== selectedSurvey) return;
    renderSummary(summary); renderTrends(series);
  } catch (error) {
    if (token === surveyRequest) document.querySelector('#message').textContent = `Survey view unavailable: ${error.message}. Displayed charts may be stale.`;
  }
}
async function refresh() {
  try {
    const [data, health] = await Promise.all([request('/api/telemetry'), request('/api/health')]);
    for (const [key] of fields) document.getElementById(key).textContent = data[key].toFixed(2);
    document.querySelector('#status').textContent = `Connected · ${health.profile} · ${health.sample_interval_seconds}s interval · ${new Date(data.timestamp).toLocaleTimeString()}`;
    document.querySelector('#position').textContent = `Fixed simulated station: ${data.latitude}, ${data.longitude}`;
    await sessions(); await updateSurvey();
  } catch (error) { document.querySelector('#status').textContent = 'Disconnected or sampler degraded · Displayed readings and charts may be stale'; }
  setTimeout(refresh, 1000);
}
refresh();
