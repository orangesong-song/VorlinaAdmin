/**
 * vadmin-011 验收截图：栏目页分区 / 首页单块 / 文章分区 / 分类卡片 / 折叠态
 * 与 verify-sections.js 同一套夹具（本地桩 8778 + Supabase 夹具）。
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
  await page.setViewport({ width: 1440, height: 1100 });
  await page.setRequestInterception(true);
  mockSb(page);
  await page.evaluateOnNewDocument(o => { try { localStorage.setItem('va_content_base', o) } catch(e){} }, ORIGIN);
  await page.goto(ORIGIN + '/index.html', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    document.getElementById('email').value = 'ops@vorlina.net';
    document.getElementById('pw').value = 'x';
    document.getElementById('loginForm').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  });
  await page.waitForFunction(() => !document.getElementById('app').hidden && document.getElementById('view').textContent.length > 200, { timeout: 15000 });

  const open = async (view, matcher) => {
    await page.evaluate(v => { location.hash = '#/' + v }, view);
    await page.waitForFunction(() => document.querySelectorAll('#view [data-opened]').length > 0, { timeout: 10000 });
    await page.evaluate(m => {
      const btns = [...document.querySelectorAll('#view [data-opened]')];
      const hit = btns.find(b => JSON.parse(b.dataset.opened)[2].indexOf(m) >= 0)
               || btns.find(b => JSON.parse(b.dataset.opened)[0].indexOf(m) >= 0);
      hit.click();
    }, matcher);
    await page.waitForFunction(() => !document.getElementById('edWrap').hidden, { timeout: 8000 });
    await new Promise(r => setTimeout(r, 350));
  };
  const shot = async (name) => { await page.screenshot({ path: path.join(DIR, name) }); console.log('ok', name) };

  /* 1 分类卡片流 */
  await page.evaluate(() => { location.hash = '#/products' });
  await page.waitForFunction(() => document.querySelectorAll('#view .ccard').length > 0, { timeout: 8000 });
  /* lazy 图从 vorlina.net 拉，等首图真的解码完成再截 —— 否则截出来是空块（假象） */
  await page.waitForFunction(() => {
    const im = document.querySelector('#view .pcard-thumb img');
    return im && im.complete && im.naturalWidth > 0;
  }, { timeout: 15000 }).catch(() => {});
  await new Promise(r => setTimeout(r, 1500));
  await shot('11-分类卡片流.png');

  /* 2 栏目页整页分区 */
  await open('pages', 'factory');
  await shot('12-栏目页-整页分区.png');

  /* 3 折叠态：收起前两个分区 */
  await page.evaluate(() => {
    document.querySelectorAll('#edBody .edsec-h').forEach((h, i) => { if (i > 0 && i < 5) h.click() });
  });
  await new Promise(r => setTimeout(r, 250));
  await shot('13-栏目页-分区折叠态.png');

  /* 4 首页单块 */
  await page.evaluate(() => document.getElementById('edClose').click());
  await open('home', '首页 · hero');
  await shot('14-首页-首屏单块.png');

  /* 5 文章分区 */
  await page.evaluate(() => document.getElementById('edClose').click());
  await open('notes', '文章 · ');
  await shot('15-文章-分区表单.png');

  /* 6 分类分区 */
  await page.evaluate(() => document.getElementById('edClose').click());
  await open('products', '分类 · ');
  await shot('16-分类-分区表单.png');

  await browser.close();
})().catch(e => { console.error('截图失败：', e); process.exit(1) });
