/**
 * vadmin-010 · 验收截图：产品卡片流 + 分区表单
 * 用法：先起 tools/serve-local.py 8778，再跑本脚本
 */
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const SB = 'https://jjmaularjtmhptbfnovd.supabase.co';
const ORIGIN = 'http://127.0.0.1:8778';
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const OUT = path.resolve(__dirname, '..', '_not-for-site', '验收截图-20260923');

(async function () {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--window-size=1440,1000'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 1000 });
  await page.setRequestInterception(true);
  page.on('request', req => {
    const u = req.url();
    if (!u.startsWith(SB)) return req.continue();
    const cors = {
      'Access-Control-Allow-Origin': ORIGIN,
      'Access-Control-Allow-Headers': req.headers()['access-control-request-headers'] || '*',
      'Access-Control-Allow-Methods': 'GET,POST,PATCH,DELETE,OPTIONS',
    };
    const body = (o, st) => req.respond({ status: st || 200, contentType: 'application/json', headers: cors, body: JSON.stringify(o) });
    if (req.method() === 'OPTIONS') return req.respond({ status: 204, headers: cors, body: '' });
    if (u.includes('/auth/v1/token?grant_type=password'))
      return body({ access_token: 'AT-1', refresh_token: 'RT-1', expires_in: 3600, user: { id: 'uid-1', email: 'ops@vorlina.net' } });
    if (u.includes('/auth/v1/user')) return body({ id: 'uid-1', email: 'ops@vorlina.net' });
    if (u.includes('/rest/v1/members')) return body([{ member_id: 'M001', name: '宋宋', role: 'boss', email: 'ops@vorlina.net' }]);
    if (u.includes('/rest/v1/inquiries')) return body([]);
    return body({});
  });
  await page.evaluateOnNewDocument(o => { try { localStorage.setItem('va_content_base', o) } catch (e) {} }, ORIGIN);
  await page.goto(ORIGIN + '/index.html', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    document.getElementById('email').value = 'ops@vorlina.net';
    document.getElementById('pw').value = 'whatever';
    document.getElementById('loginForm').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  });
  await page.waitForFunction(() => !document.getElementById('app').hidden && document.getElementById('view').textContent.length > 200, { timeout: 15000 });
  await page.evaluate(() => { location.hash = '#/products' });
  await page.waitForFunction(() => document.querySelectorAll('#view .pcard').length > 0, { timeout: 10000 });
  await new Promise(r => setTimeout(r, 800));
  await page.screenshot({ path: path.join(OUT, '01-产品卡片流.png'), fullPage: false });

  await page.evaluate(() => document.querySelector('#view .pcard [data-opened]').click());
  await page.waitForFunction(() => !document.getElementById('edWrap').hidden, { timeout: 8000 });
  await new Promise(r => setTimeout(r, 900));
  await page.screenshot({ path: path.join(OUT, '02-分区表单-基础信息.png') });
  await page.evaluate(() => { document.getElementById('edBody').scrollTop = 99999 });
  await new Promise(r => setTimeout(r, 700));
  await page.screenshot({ path: path.join(OUT, '03-分区表单-图片区.png') });
  await browser.close();
  console.log('截图已存 →', OUT);
})().catch(e => { console.error(e); process.exit(1) });
