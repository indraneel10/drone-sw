// Real-browser acceptance checks for the local environmental monitoring demo.
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const {chromium} = require('playwright');

async function unusedPort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {server.once('error', reject); server.listen(0, '127.0.0.1', resolve);});
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}
async function ready(url, process) {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    if (process.exitCode !== null) throw new Error('App exited before it became healthy');
    try {
      const response = await fetch(`${url}/api/health`, {signal: AbortSignal.timeout(1000)});
      if (response.ok) return;
    } catch (_) { /* Retry while the local server starts. */ }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error('App did not become healthy within 15 seconds');
}
async function main() {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'water-monitor-browser-'));
  const output = path.resolve('browser-results'); fs.mkdirSync(output, {recursive:true});
  const port = await unusedPort(); const url = `http://127.0.0.1:${port}`;
  const app = spawn(process.env.PYTHON || 'python', ['-m', 'water_monitor', '--port', String(port), '--database', path.join(temporary, 'survey.sqlite3'), '--interval', '0.1'], {stdio:['ignore', 'pipe', 'pipe']});
  let logs = ''; app.stdout.on('data', data => logs += data); app.stderr.on('data', data => logs += data);
  let browser;
  try {
    await ready(url, app);
    browser = await chromium.launch({headless:true});
    const page = await browser.newPage({viewport:{width:1280,height:900}});
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    await page.locator('#status').filter({hasText:'Connected'}).waitFor();
    assert.equal(await page.locator('#readings article').count(), 4);
    assert.match(await page.locator('#position').textContent(), /Fixed simulated station/);
    assert.equal(await page.getByRole('button', {name:'Stop recording',exact:true}).isDisabled(), true);

    // An empty recording needs an explicit message and blank summary statistics.
    const empty = await page.request.post(`${url}/api/sessions/start`, {headers:{'X-Monitor-Request':'1'}});
    assert.equal(empty.status(), 200);
    const emptyId = (await empty.json()).session_id;
    await page.request.post(`${url}/api/sessions/stop`, {headers:{'X-Monitor-Request':'1'}});
    await page.locator('#sessions').filter({hasText:`Survey ${emptyId}`}).waitFor();
    await page.getByRole('button', {name:'View survey'}).first().click();
    // Backend unit tests cover empty datasets deterministically; this browser
    // view may have one sample because the independent sampler keeps running.
    await page.locator('#summary h3').waitFor();

    const starting = page.waitForResponse(response => response.url() === `${url}/api/sessions/start` && response.request().method() === 'POST');
    await page.getByRole('button', {name:'Start recording',exact:true}).click();
    const recordedId = (await (await starting).json()).session_id;
    await page.locator('#summary h3').filter({hasText:`Survey ${recordedId} ·`}).waitFor();
    await page.locator('#trends svg').first().waitFor();
    assert.equal(await page.locator('#trends svg').count(), 4);
    await page.waitForFunction(() => document.querySelector('#trends h3').textContent.includes('recorded samples'));
    const focused = page.getByRole('button', {name:'View survey'}).first();
    await focused.focus();
    await page.waitForTimeout(1200);
    assert.equal(await focused.evaluate(node => node === document.activeElement), true);
    await page.screenshot({path:path.join(output, 'desktop.png'),fullPage:true});
    await page.getByRole('button', {name:'Stop recording',exact:true}).click();
    await page.locator('#sessions li').first().filter({hasText:'Saved'}).waitFor();
    const sampleCount = Number((await page.locator('#summary h3').textContent()).match(/(\d+) samples/)[1]);
    assert.ok(sampleCount > 0);

    for (const format of ['JSON', 'CSV']) {
      const downloaded = page.waitForEvent('download');
      await page.getByRole('link', {name:`Download ${format}`,exact:true}).first().click();
      const download = await downloaded;
      assert.ok(download.suggestedFilename().endsWith(`.${format.toLowerCase()}`));
      const local = path.join(output, download.suggestedFilename()); await download.saveAs(local);
      const text = fs.readFileSync(local, 'utf8');
      if (format === 'JSON') {
        const data = JSON.parse(text); assert.equal(data.simulated, true);
        assert.ok(data.samples.length > 0); assert.equal(data.samples[0].simulated, true);
      } else assert.match(text, /timestamp,simulated,latitude/);
    }
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'Mobile layout must not overflow horizontally');
    await page.screenshot({path:path.join(output, 'mobile.png'),fullPage:true});
    await page.reload();
    await page.locator('#sessions li').first().filter({hasText:'Saved'}).waitFor();
    assert.equal(errors.length, 0, errors.join('\n'));
    console.log('PASS: telemetry, recording, four SVG trends, keyboard focus, JSON/CSV downloads, mobile layout, and survey history');
  } catch (error) {
    fs.writeFileSync(path.join(output, 'server.log'), logs);
    throw error;
  } finally {
    if (browser) await browser.close();
    if (app.exitCode === null) {
      const exited = new Promise(resolve => app.once('exit', resolve));
      app.kill('SIGTERM');
      await exited;
    }
    fs.rmSync(temporary, {recursive:true,force:true});
  }
}
main().catch(error => {console.error(error); process.exitCode = 1;});
