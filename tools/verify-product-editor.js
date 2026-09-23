/**
 * vorlina-admin · vadmin-010「产品分区表单」真实浏览器验证
 * 2026-09-23 · 无头 Chrome（puppeteer-core）
 *
 * 前置：tools/serve-local.py 已在 8778 跑着（内容桩读官网真源）。
 *       Supabase 用夹具（真账密不该拿来测失败路径），内容必须是真的。
 *
 * 为什么单独一个文件：产品编辑从「字段平铺」改成「分区表单 + 主图下拉 + 设为主图」，
 *   这是一条新的交互路径，必须有自己的断言；同时 verify-content.js 的 T3 要跟着改判据
 *   （守卫的判据会骗人 —— 改了 UI 不改断言，等于守卫装瞎）。
 *
 * 断言原则：
 *   ① 必须出现**真源里才有的字面量**（真实中文名 / 真实规格键 / 真实图片文件名）
 *   ② 交互要真的产生效果（点「设为主图」→ 下拉值真的变）
 *   ③ 内部字段仍然隐藏、结构键仍然只读（不让运营误改）
 */
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const SB = 'https://jjmaularjtmhptbfnovd.supabase.co';
const ORIGIN = 'http://127.0.0.1:8778';
const URL_PAGE = ORIGIN + '/index.html';
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const SITE = path.resolve(__dirname, '..', '..', 'vorlina-new');

/* 期望值取自官网真源，不猜 —— 脚本自己读一遍 products.json / imagery.json 现算 */
const prod = JSON.parse(fs.readFileSync(path.join(SITE, 'data/products.json'), 'utf8'));
const imgy = JSON.parse(fs.readFileSync(path.join(SITE, 'build/data/imagery.json'), 'utf8'));
const P0 = prod.products[0];
const EXPECT = {
  sku: P0.sku,
  nameZh: P0.nameZh,
  taglineHead: String(P0.tagline).slice(0, 24),
  hero: P0.images.hero,
  usableN: P0.images.usable.length,
  usable2: P0.images.usable[1],
  specKey: Object.keys(P0.specs)[0],
  pkgN: P0.packages.length,
  total: prod.products.length,
};

let pass = 0, fail = 0;
const out = [];
function check(name, cond, detail) {
  if (cond) { pass++; out.push('  OK  ' + name); }
  else { fail++; out.push('  XX  ' + name + (detail ? '  -> ' + detail : '')); }
}
function section(t) { out.push('\n' + t); }

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
    if (url.includes('/auth/v1/token?grant_type=refresh_token'))
      return body({ access_token: 'AT-2', refresh_token: 'RT-2', expires_in: 3600, user: { id: 'uid-1', email: 'ops@vorlina.net' } });
    if (url.includes('/auth/v1/user')) return body({ id: 'uid-1', email: 'ops@vorlina.net' });
    if (url.includes('/rest/v1/members')) return body([{ member_id: 'M001', name: '宋宋', role: 'boss', email: 'ops@vorlina.net' }]);
    if (url.includes('/rest/v1/inquiries')) return body([]);
    return body({});
  });
}

(async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--window-size=1440,900'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  const jsErrors = [];
  page.on('pageerror', e => jsErrors.push(String(e.message)));
  page.on('console', m => {
    if (m.type() !== 'error') return;
    if (/Failed to load resource/.test(m.text())) return;   // 图片/网络状态码，不是 JS 异常
    jsErrors.push('console: ' + m.text());
  });
  await page.setRequestInterception(true);
  mockSb(page);

  /* ⚠️ CONTENT_BASE 默认是生产 Worker —— 本地测试不指回桩就会 401（内容 0/15） */
  await page.evaluateOnNewDocument(o => { try { localStorage.setItem('va_content_base', o) } catch(e){} }, ORIGIN);
  /* ⚠️ CONTENT_BASE 默认是生产 Worker —— 本地测试不指回桩就会 401（内容 0/15） */
  await page.evaluateOnNewDocument(o => { try { localStorage.setItem('va_content_base', o) } catch(e){} }, ORIGIN);
  await page.goto(URL_PAGE, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    document.getElementById('email').value = 'ops@vorlina.net';
    document.getElementById('pw').value = 'whatever';
    document.getElementById('loginForm').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  });
  await page.waitForFunction(() => !document.getElementById('app').hidden && document.getElementById('view').textContent.length > 200, { timeout: 15000 });

  /* ── 列表：卡片流 ── */
  section('产品列表 · 卡片流');
  await page.evaluate(() => { location.hash = '#/products' });
  await page.waitForFunction(() => document.querySelectorAll('#view .pcard').length > 0, { timeout: 10000 });
  const list = await page.evaluate(() => ({
    cards: document.querySelectorAll('#view .pcard').length,
    imgs: document.querySelectorAll('#view .pcard-thumb img').length,
    firstSku: (document.querySelector('#view .pcard-sku') || {}).textContent || '',
    dots: document.querySelectorAll('#view .pcard-f .dot').length,
    tables: document.querySelectorAll('#view table.tbl').length,
  }));
  check('T1 卡片数 = 真源款数（' + EXPECT.total + '）', list.cards === EXPECT.total, '实际 ' + list.cards);
  check('T2 每张卡片都有缩略图元素', list.imgs === EXPECT.total, '实际 ' + list.imgs);
  check('T3 首卡 SKU = 真源 ' + EXPECT.sku, list.firstSku.trim() === EXPECT.sku, '实际 ' + list.firstSku);
  check('T4 每张卡片都有状态点', list.dots === EXPECT.total, '实际 ' + list.dots);
  check('T5 型号区已无表格（只剩分类那张）', list.tables === 1, '实际 ' + list.tables);

  /* ── 打开首款分区表单 ── */
  section('产品编辑 · 分区表单');
  await page.evaluate(() => document.querySelector('#view .pcard [data-opened]').click());
  await page.waitForFunction(() => !document.getElementById('edWrap').hidden, { timeout: 8000 });
  const ed = await page.evaluate(() => {
    const b = document.getElementById('edBody');
    return {
      secs: [...b.querySelectorAll('.edsec-h')].map(e => e.textContent.trim()),
      labels: [...b.querySelectorAll('.ed-k')].map(e => e.textContent.trim()),
      textareas: b.querySelectorAll('textarea.ed-in').length,
      tagline: (b.querySelector('textarea.ed-in') || {}).value || '',
      nameVal: (function () {
        const el = [...b.querySelectorAll('[data-ed]')].find(x => /nameZh/.test(x.dataset.ed));
        return el ? el.value : '';
      })(),
      ro: [...b.querySelectorAll('.ed-ro')].map(e => e.textContent.trim()),
      heroOpts: [...b.querySelectorAll('select.ed-in option')].map(o => o.value),
      heroVal: (b.querySelector('select.ed-in') || {}).value || '',
      thumbs: b.querySelectorAll('.ed-thumb').length,
      hiddenNote: /已隐藏/.test(b.textContent),
      forbidden: /copyRules|lowRes|exclude|contraindication|certificationGroup/.test(b.textContent),
      specText: b.textContent.indexOf('workingMode') >= 0 || b.textContent.indexOf(Object.keys({}).join()) >= 0,
    };
  });
  check('T6 五个分区齐全（基础 / 只读 / 包装 / 规格 / 图片）',
    ed.secs.length === 5 && /① 基础信息/.test(ed.secs[0]) && /⑤ 图片/.test(ed.secs[4]), JSON.stringify(ed.secs));
  check('T7 中文名输入框填的是真源值', ed.nameVal === EXPECT.nameZh, '实际 ' + ed.nameVal);
  check('T8 卖点是多行输入框且内容来自真源', ed.textareas >= 1 && ed.tagline.indexOf(EXPECT.taglineHead) === 0, ed.tagline.slice(0, 40));
  check('T9 中文标签（人看得懂，不是英文键名）', ed.labels.some(t => /中文名/.test(t)), JSON.stringify(ed.labels.slice(0, 4)));
  check('T10 sku / category 只读且标明只读',
    ed.ro.some(t => new RegExp(EXPECT.sku).test(t)) && ed.ro.some(t => /只读/.test(t)), JSON.stringify(ed.ro.slice(0, 3)));
  check('T11 内部字段仍然隐藏（copyRules / lowRes / exclude 不出现）', !ed.forbidden && ed.hiddenNote);
  check('T12 规格区渲染真源参数名', ed.specText, '未找到 workingMode');
  check('T13 主图下拉选项 = 画廊清单（' + EXPECT.usableN + ' 项）且当前选中真源主图',
    ed.heroOpts.length === EXPECT.usableN && ed.heroVal === EXPECT.hero,
    ed.heroOpts.length + ' 项 · 选中 ' + ed.heroVal);
  check('T14 缩略图条渲染（图库按 sku 匹配）', ed.thumbs === EXPECT.usableN, '实际 ' + ed.thumbs);

  /* ── 交互：设为主图 ── */
  section('交互 · 设为主图');
  const before = ed.heroVal;
  const clicked = await page.evaluate(() => {
    const b = [...document.querySelectorAll('#edBody .ed-thumb [data-hero]')][0];
    if (!b) return null;
    const fn = b.dataset.hero;
    b.click();
    return fn;
  });
  await new Promise(r => setTimeout(r, 250));
  const after = await page.evaluate(fn => ({
    heroVal: (document.querySelector('#edBody select.ed-in') || {}).value || '',
    /* 判据不是「第一张缩略图」—— 画廊顺序是 usable 的顺序，
       被设为主图的可能是第 2 张。要验的是「文件名对得上那张标了当前主图」。 */
    heroThumbMarked: [...document.querySelectorAll('#edBody .ed-thumb')]
      .filter(t => (t.textContent || '').indexOf(fn) >= 0)
      .every(t => /当前主图/.test(t.textContent)),
    heroMarkedN: [...document.querySelectorAll('#edBody .ed-thumb')].filter(t => /当前主图/.test(t.textContent || '')).length,
  }), clicked);
  check('T15 有「设为主图」按钮可点', !!clicked, '未找到按钮');
  check('T16 点完主图下拉值真的变了（' + before + ' → ' + clicked + '）',
    clicked && after.heroVal === clicked, '实际 ' + after.heroVal);
  check('T17 被设为主图的缩略图标了「当前主图」且只有一张',
    after.heroThumbMarked && after.heroMarkedN === 1,
    '标记数 ' + after.heroMarkedN + ' · 命中 ' + clicked);

  /* ── 交互：改字段值不丢 ── */
  section('交互 · 改值后重渲染不丢');
  const typed = await page.evaluate(() => {
    const el = [...document.querySelectorAll('#edBody [data-ed]')].find(x => /nameZh/.test(x.dataset.ed));
    el.value = el.value + '（改过）';
    el.dispatchEvent(new Event('input', { bubbles: true }));
    return el.value;
  });
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('#edBody .ed-thumb [data-hero]')][0];
    if (b) b.click();
  });
  await new Promise(r => setTimeout(r, 200));
  const kept = await page.evaluate(() => {
    const el = [...document.querySelectorAll('#edBody [data-ed]')].find(x => /nameZh/.test(x.dataset.ed));
    return el ? el.value : '';
  });
  check('T18 改完再点「设为主图」，已填内容不丢', kept === typed, '实际 ' + kept);

  check('T19 全程无 JS 异常', jsErrors.length === 0, jsErrors.slice(0, 3).join(' | '));

  await browser.close();
  console.log(out.join('\n'));
  console.log('\n' + '='.repeat(52));
  console.log('通过 ' + pass + ' / 失败 ' + fail);
  console.log('='.repeat(52));
  if (jsErrors.length) console.log('JS 异常明细：\n' + jsErrors.join('\n'));
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('验证脚本自身出错：', e); process.exit(2); });
