/**
 * vadmin-013 验收截图：媒体库（上传区 + 已上传 + 仓库图库）
 * 与 verify-media.js 同一套夹具（本地桩 8778 + Supabase 夹具）。
 */
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const SB = 'https://jjmaularjtmhptbfnovd.supabase.co';
const ORIGIN = 'http://127.0.0.1:8778';
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const DIR = path.resolve(__dirname, '..', '_not-for-site', '验收截图-20260923');
fs.mkdirSync(DIR, { recursive: true });

function mockSb(page) {
  return page.on('request', req => {
    const url = req.url();
    if (!url.startsWith(SB)) return req.continue();
    const cors = {
      'Access-Control-Allow-Origin': ORIGIN,
      'Access-Control-Allow-Headers': req.headers()['access-control-request-headers'] || '*',
      'Access-Control-Allow-Methods': 'GET,POST,PATCH,DELETE,OPTIONS',
    };
    const body = (o, st) => req.respond({ status: st || 200, contentType: 'application/json', headers: cors, body: JSON.stringify(o) });
    if (req.method() === 'OPTIONS') return req.respond({ status: 204, headers: cors, body: '' });
    if (url.includes('/auth/v1/token?grant_type=password'))
      return body({ access_token: 'AT-1', refresh_token: 'RT-1', expires_in: 3600, user: { id: 'uid-1', email: 'ops@vorlina.net' } });
    if (url.includes('/auth/v1/user')) return body({ id: 'uid-1', email: 'ops@vorlina.net' });
    if (url.includes('/rest/v1/members')) return body([{ member_id: 'M001', name: '宋宋', role: 'boss', email: 'ops@vorlina.net' }]);
    if (url.includes('/rest/v1/inquiries')) return body([]);
    return body({});
  });
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 1150 });
  await page.setRequestInterception(true);
  mockSb(page);
  await page.evaluateOnNewDocument(o => { try { localStorage.setItem('va_content_base', o) } catch (e) {} }, ORIGIN);
  await page.goto(ORIGIN + '/index.html', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    document.getElementById('email').value = 'ops@vorlina.net';
    document.getElementById('pw').value = 'x';
    document.getElementById('loginForm').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  });
  await page.waitForFunction(() => !document.getElementById('app').hidden && document.getElementById('view').textContent.length > 200, { timeout: 15000 });

  const shot = async (name) => {
    await page.screenshot({ path: path.join(DIR, name), fullPage: false });
    console.log('  ' + name);
  };

  await page.evaluate(() => { location.hash = '#/media' });
  await page.waitForFunction(() => document.getElementById('mzone'), { timeout: 10000 });
  await page.waitForFunction(() => typeof MEDIA !== 'undefined' && MEDIA.loaded && !MEDIA.loading, { timeout: 15000 });
  /* 等缩略图解码完再截 —— 只等 400ms 会截到一堆空块（vadmin-011 踩过） */
  await page.waitForFunction(
    () => [...document.querySelectorAll('#view .mcard-thumb img')].slice(0, 12).every(i => i.complete && i.naturalWidth > 0),
    { timeout: 30000 }).catch(() => {});
  await new Promise(r => setTimeout(r, 600));
  await shot('20-媒体库-上传区与仓库图库.png');

  await page.evaluate(() => window.scrollTo(0, 620));
  await new Promise(r => setTimeout(r, 900));
  await page.waitForFunction(
    () => [...document.querySelectorAll('#view .mcard-thumb img')].slice(0, 24).every(i => i.complete && i.naturalWidth > 0),
    { timeout: 30000 }).catch(() => {});
  await shot('21-媒体库-仓库图库网格.png');

  await browser.close();
  console.log('截图完成 → ' + DIR);
})().catch(e => { console.error('FATAL', e); process.exit(2) });
