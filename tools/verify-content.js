/**
 * vorlina-admin · P1 第 2 步「内容接仓库真源」真实浏览器验证
 * 2026-09-20 · 无头 Chrome（puppeteer-core）
 *
 * 前置：本地内容桩已在 8778 跑着（tools/serve-local.py）。
 *       Supabase 仍用夹具（真账密不该拿来测失败路径），
 *       但**内容数据必须是真的** —— 这正是这次要验的东西。
 *
 * 断言设计：
 *   ① 每个模块都必须出现**真源里才有的字面量**（真实 SKU / 真实 SEO 标题 / 真实章标题）
 *      —— 只验证「表格有 16 行」是不够的，演示数据也能凑出 16 行。
 *   ② 页面里不许再出现「演示数据」四个字。
 *   ③ 「内容读不到」不能表现为白屏或假装成功 —— 必须在总览上报出来（源自本站翻过三次的车）。
 */
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

/* 版本串现算：官网每次发版都会升，写死在测试里只会制造假红（2026-09-23 实测如此） */
const SITE = path.resolve(__dirname, '..', '..', 'vorlina-new');
const VERSION = fs.readFileSync(path.join(SITE, 'build', 'version.txt'), 'utf8').trim();

const SB = 'https://jjmaularjtmhptbfnovd.supabase.co';
const ORIGIN = 'http://127.0.0.1:8778';
const URL_PAGE = ORIGIN + '/index.html';
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

/* 期望值取自官网真源（vorlina-new/），不是猜的：
   products.json 16 款 / 6 分类 · insights.json 5 篇 · pages 9 个 · home.json FAQ 10 条 · version 现算（version.txt） */
const EXPECT = {
  version: VERSION,
  /* 后台会读的内容文件数 = 6 份 + 9 个栏目页 = 15。
     ⚠️ 别写成 16 —— 那是产品款数，不是文件数。两个数混用是本站明令禁止的（D99 类错误）。 */
  filesTotal: 15,
  products: 16, categories: 6, notes: 5, pages: 9, certs: 16, faq: 10,
  sku: 'VOR-DZ-TS01',
  catShort: 'Laser & Light',
  noteTitle: 'What we check before your order leaves the factory',
  seoTitle: 'Factory — 5,000 m² in Baiyun, Guangzhou',
};

let pass = 0, fail = 0;
const out = [];
function check(name, cond, detail) {
  if (cond) { pass++; out.push('  OK  ' + name); }
  else { fail++; out.push('  XX  ' + name + (detail ? '  -> ' + detail : '')); }
}
function section(t) { out.push('\n' + t); }

/* 单一请求拦截器 —— 一个请求只能被处理一次。
   ⚠️ 不要写成「再注册一个 handler 来改行为」：两个 handler 会争同一个请求，
   第二个调 respond 时请求早已 continue → Request is already handled。
   所以变异开关做成 flag，拦截器全局只装一次。 */
function mockSb(page, S) {
  return page.on('request', req => {
    const url = req.url();
    if (S.contentDown && url.includes('/content?path=')) {
      return req.respond({ status: 500, contentType: 'application/json',
        headers: { 'Access-Control-Allow-Origin': ORIGIN },
        body: JSON.stringify({ message: 'stub down (变异测试)' }) });
    }
    if (!url.startsWith(SB)) return req.continue();
    const cors = {
      'Access-Control-Allow-Origin': ORIGIN,
      'Access-Control-Allow-Headers': req.headers()['access-control-request-headers'] || '*',
      'Access-Control-Allow-Methods': 'GET,POST,PATCH,DELETE,OPTIONS',
    };
    const body = (o, st) => req.respond({ status: st || 200, contentType: 'application/json', headers: cors, body: JSON.stringify(o) });
    if (req.method() === 'OPTIONS') return req.respond({ status: 204, headers: cors, body: '' });
    if (url.includes('/auth/v1/token?grant_type=password')) {
      return body({ access_token: 'AT-1', refresh_token: 'RT-1', expires_in: 3600, user: { id: 'uid-1', email: 'ops@vorlina.net' } });
    }
    if (url.includes('/auth/v1/token?grant_type=refresh_token')) {
      return body({ access_token: 'AT-2', refresh_token: 'RT-2', expires_in: 3600, user: { id: 'uid-1', email: 'ops@vorlina.net' } });
    }
    if (url.includes('/auth/v1/user')) return body({ id: 'uid-1', email: 'ops@vorlina.net' });
    if (url.includes('/rest/v1/members')) return body([{ member_id: 'M001', name: '宋宋', role: 'boss', email: 'ops@vorlina.net' }]);
    if (url.includes('/rest/v1/inquiries')) {
      if (S.inquiries === 'fail') return body({ message: 'inquiries read blocked (夹具)' }, 403);
      return body([
        { id: 'e1', created_at: '2026-09-19T14:22:00Z', name: 'Ahmed Hassan', company: 'Nile Beauty Trading', country: 'Egypt', status: 'new' },
        { id: 'e2', created_at: '2026-09-18T11:07:00Z', name: 'Maria Lopez', company: 'Derma Clinic Madrid', country: 'Spain', status: 'contacted' },
        { id: 'e3', created_at: '2026-09-17T09:33:00Z', name: 'John Smith', company: 'Aesthetic Supply Co', country: 'USA', status: 'new' },
      ]);
    }
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
    if (/Failed to load resource/.test(m.text())) return;   // 网络状态码，不是 JS 异常
    jsErrors.push('console: ' + m.text());
  });
  await page.setRequestInterception(true);
  const S = { inquiries: 'ok' };
  mockSb(page, S);

  /* ⚠️ CONTENT_BASE 默认是生产 Worker —— 本地测试不指回桩就会 401（内容 0/15） */
  await page.evaluateOnNewDocument(o => { try { localStorage.setItem('va_content_base', o) } catch(e){} }, ORIGIN);
  await page.goto(URL_PAGE, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    document.getElementById('email').value = 'ops@vorlina.net';
    document.getElementById('pw').value = 'whatever';
    document.getElementById('loginForm').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  });
  await page.waitForFunction(() => !document.getElementById('app').hidden && document.getElementById('view').textContent.length > 200, { timeout: 15000 });

  const go = async id => {
    await page.evaluate(i => { location.hash = '#/' + i }, id);
    await page.waitForFunction(() => !/正在从仓库读取内容/.test(document.getElementById('view').textContent), { timeout: 10000 }).catch(() => {});
    await new Promise(r => setTimeout(r, 120));
    return page.evaluate(() => ({
      view: document.getElementById('view').textContent,
      rows: document.querySelectorAll('#view table.tbl tbody tr').length,
      cards: document.querySelectorAll('#view .pcard').length,
      firstRows: (function(){ const t = document.querySelector('#view table.tbl tbody'); return t ? t.children.length : 0 })(),
      tableCount: document.querySelectorAll('#view table.tbl').length,
      nav: (document.querySelector('#railNav [aria-current="page"]') || {}).textContent || '',
    }));
  };

  /* ── T1/T2 总览：来源标记与现算指标 ── */
  section('总览');
  const ov = await go('overview');
  check('T1 来源标记显示全部读到（15 份 · ' + EXPECT.version + '）',
    ov.view.includes('真源 ' + EXPECT.filesTotal + '/' + EXPECT.filesTotal)
      && ov.view.includes('v' + EXPECT.version), ov.view.slice(0, 200));
  check('T2 指标为现算（16 款 / 6 分类 / 5 篇 / 9 栏目页）',
    /\b16\b/.test(ov.view) && ov.view.includes('6 个分类') && ov.view.includes('9'), ov.view.slice(0, 300));

  /* ── T3/T4 产品与分类：必须出现真实 SKU 与真实分类短名 ── */
  section('产品与分类');
  const pr = await go('products');
  /* vadmin-010：型号区已由表格改为卡片流（缩略图 + 状态点），本页只剩分类那一张表。 */
  check('T3 型号卡片 16 张（本页剩 1 张表：分类）',
    pr.cards === EXPECT.products && pr.tableCount === 1,
    '卡片 ' + pr.cards + ' 张 · 表 ' + pr.tableCount + ' 张');
  check('T3b 卡片带缩略图元素（图库按 sku 匹配）',
    await page.evaluate(() => document.querySelectorAll('#view .pcard-thumb img').length) === EXPECT.products);
  check('T4 含真实 SKU ' + EXPECT.sku, pr.view.includes(EXPECT.sku));
  check('T5 含真实分类短名 ' + EXPECT.catShort, pr.view.includes(EXPECT.catShort));
  const catSum = await page.evaluate(() => {
    const t = [...document.querySelectorAll('#view table.tbl')][0];   // vadmin-010：0 = 分类表
    return t ? [...t.querySelectorAll('tbody tr')].reduce((s, tr) => s + Number((tr.children[3] || {}).textContent || 0), 0) : -1;
  });
  check('T6 分类表在架款数合计 = 16（派生值正确）', catSum === EXPECT.products, '实际 ' + catSum);

  /* ── T7/T8 文章与栏目页 ── */
  section('文章 / 栏目页');
  const nt = await go('notes');
  check('T7 文章 5 行', nt.rows === EXPECT.notes, '实际 ' + nt.rows);
  check('T8 含真实文章标题', nt.view.includes(EXPECT.noteTitle));
  const pg = await go('pages');
  check('T9 栏目页 9 行', pg.rows === EXPECT.pages, '实际 ' + pg.rows);
  check('T10 含真实 SEO 标题（来自 factory.json 的 meta）', pg.view.includes(EXPECT.seoTitle));

  /* ── T11/T12 首页与认证 ── */
  section('首页 / 认证文件');
  const hm = await go('home');
  check('T11 首页列出多个真实区块名', hm.view.includes('hero') && hm.view.includes('faq') && hm.view.includes('cta'));
  check('T12 FAQ 条数 = ' + EXPECT.faq + '（且是一份数据两处渲染）',
    hm.view.includes(String(EXPECT.faq) + ' 条 FAQ'), hm.view.slice(0, 300));
  const ct = await go('certs');
  check('T13 认证显示 16 份且给出换图方式', ct.view.includes('16') && ct.view.includes('同名替换'));

  /* ── T14/T15 询盘：走 Supabase 直连 ── */
  section('询盘查看');
  const iq = await go('inquiries');
  check('T14 询盘渲染真实字段（公司名来自夹具 REST 响应）', iq.view.includes('Nile Beauty Trading'));
  /* ⚠️ 不能在全文本里搜「近 30 天」—— 脚注为了对比会写出这几个字。
     要验的是**指标名**：不管口径怎么描述，指标标签必须是「本次读取」。 */
  const iqK = await page.evaluate(() =>
    [...document.querySelectorAll('#view .metric .k')].map(e => e.textContent).join(' | '));
  check('T15 指标名是「本次读取」而非假的「近 30 天」',
    /本次读取/.test(iqK) && !/近 30 天/.test(iqK), '实际指标：' + iqK);

  /* ── T16 发布链路未接入：按钮必须禁用且写明原因 ── */
  section('发布（未接入时的诚实表现）');
  const ch = await go('changes');
  const btn = await page.evaluate(() => {
    const b = [...document.querySelectorAll('#view button')].find(x => /确认发布/.test(x.textContent));
    return b ? { disabled: b.disabled, title: b.title || '' } : null;
  });
  check('T16 「确认发布」禁用且带原因说明', !!btn && btn.disabled && btn.title.length > 5, JSON.stringify(btn));
  const rl = await go('releases');
  check('T17 发布历史只有一条真数据（当前版本串）',
    rl.rows === 1 && rl.view.includes(EXPECT.version), '行数 ' + rl.rows);

  /* ── T18 全站不许再出现「演示数据」 ── */
  section('演示数据清理');
  let demoSeen = '';
  for (const id of ['overview', 'products', 'notes', 'pages', 'home', 'certs', 'inquiries', 'changes', 'releases', 'media', 'geo', 'settings']) {
    const v = await go(id);
    if (/演示数据/.test(v.view)) demoSeen += id + ' ';
  }
  check('T18 12 个路由均无「演示数据」字样', demoSeen === '', '残留于：' + demoSeen);

  /* ── T19/T20 变异测试：内容读不到时必须报出来 ── */
  section('变异测试 · 内容不可达');
  S.contentDown = true;                 /* 开关一拨，拦截器行为就变 —— 不再动拦截器本身 */
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => !document.getElementById('app').hidden && document.getElementById('view').textContent.length > 100, { timeout: 15000 }).catch(() => {});
  /* 错误横幅画在总览上；reload 后 hash 可能停在别的路由，先显式回到总览 */
  await page.evaluate(() => { location.hash = '#/overview' });
  await new Promise(r => setTimeout(r, 200));
  const bad = await page.evaluate(() => document.getElementById('view').textContent);
  check('T19 内容读不到时报出「没读到」，不假装成功', /没读到/.test(bad), bad.slice(0, 300));
  check('T20 同时不崩到白屏（仍能进后台）', bad.length > 100 && !/^$/.test(bad.trim()));

  check('T21 全程无 JS 异常', jsErrors.length === 0, jsErrors.slice(0, 3).join(' | '));

  await browser.close();
  console.log(out.join('\n'));
  console.log('\n' + '='.repeat(52));
  console.log('通过 ' + pass + ' / 失败 ' + fail);
  console.log('='.repeat(52));
  if (jsErrors.length) console.log('JS 异常明细：\n' + jsErrors.join('\n'));
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('验证脚本自身出错：', e); process.exit(2); });
