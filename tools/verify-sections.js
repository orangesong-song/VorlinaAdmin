/**
 * vorlina-admin · vadmin-011「分区表单推广到栏目页 / 首页 / 文章 / 分类」真实浏览器验证
 * 2026-09-23 · 无头 Chrome（puppeteer-core）
 *
 * 前置：tools/serve-local.py 已在 8778 跑着（内容桩读官网真源）。
 *       Supabase 用夹具（真账密不该拿来测失败路径），内容必须是真的。
 *
 * 断言原则（与 verify-product-editor.js 同一条纪律）：
 *   ① 必须出现**真源里才有的字面量**（真实 SEO 标题 / 真实 slug / 真实首页 h1 片段 / 真实文章标题）
 *   ② 中文标签真生效 —— 分区标题不能是裸键名（pageHead / cardImage 这类只能出现在 mono 小字里）
 *   ③ 内部字段仍隐藏（_note / _rules / pvbar 不出现在编辑区）
 *   ④ 结构键只读（slug 只出现在只读行里，没有可编辑输入框）
 *   ⑤ 交互真有效（点分区标题 → 真的折叠）
 *   ⑥ 全程无 JS 异常
 */
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const SB = 'https://jjmaularjtmhptbfnovd.supabase.co';
const ORIGIN = 'http://127.0.0.1:8778';
const URL_PAGE = ORIGIN + '/index.html';
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const SITE = path.resolve(__dirname, '..', '..', 'vorlina-new');

/* 期望值一律从真源现算，不写死 —— 写死的期望值会随真源漂移变成假红（vadmin-010 已踩过一次） */
const factory = JSON.parse(fs.readFileSync(path.join(SITE, 'content/pages/factory.json'), 'utf8'));
const home = JSON.parse(fs.readFileSync(path.join(SITE, 'content/home.json'), 'utf8'));
const ins = JSON.parse(fs.readFileSync(path.join(SITE, 'build/data/insights.json'), 'utf8'));
const prod = JSON.parse(fs.readFileSync(path.join(SITE, 'data/products.json'), 'utf8'));
const N0 = ins.notes[0], C0 = prod.categories[0];
const EXPECT = {
  seoTitle: factory.meta.title,
  /* pvbar（预览条）在 PAGES_SCHEMA.deny 里，整段隐藏 —— 分区数 = 顶层非 `_` 键数 - deny 数 */
  factoryBlocks: Object.keys(factory).filter(k => !k.startsWith('_') && k !== 'pvbar').length,
  heroKick: home.hero.kick,
  heroImg: home.hero.img,
  noteTitle: N0.title,
  noteSlug: N0.slug,
  noteImage: N0.image,
  catSlug: C0.slug,
  catZh: C0.zh,
  catImg: C0.cardImage,
  cats: prod.categories.length,
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

/* 打开某个视图里第 n 个「改」按钮（data-opened 带路径与 sub） */
async function openEditor(page, view, matcher) {
  await page.evaluate(v => { location.hash = '#/' + v }, view);
  await page.waitForFunction(() => document.querySelectorAll('#view [data-opened]').length > 0, { timeout: 10000 });
  await page.evaluate(m => {
    const btns = [...document.querySelectorAll('#view [data-opened]')];
    const hit = btns.find(b => JSON.parse(b.dataset.opened)[2].indexOf(m) >= 0)
             || btns.find(b => JSON.parse(b.dataset.opened)[0].indexOf(m) >= 0);
    if (!hit) throw new Error('找不到编辑入口：' + m);
    hit.click();
  }, matcher);
  await page.waitForFunction(() => !document.getElementById('edWrap').hidden, { timeout: 8000 });
  await new Promise(r => setTimeout(r, 150));
}

const edState = page => page.evaluate(() => {
  const b = document.getElementById('edBody');
  const secs = [...b.querySelectorAll('.edsec')];
  const inputs = [...b.querySelectorAll('[data-ed]')];
  return {
    title: document.getElementById('edTitle').textContent,
    secTitles: secs.map(s => (s.querySelector('.edsec-h span') || {}).textContent || ''),
    secCount: secs.length,
    /* ⚠️ input / textarea 的值不在 textContent 里（运营看到的是 value）—— 不把 value 算进来，
       所有「真源字面量必须出现」的断言都会假红。 */
    text: b.textContent + ' \u0001 ' + [...b.querySelectorAll('input,textarea')].map(e => e.value).join(' \u0001 '),
    roText: [...b.querySelectorAll('.ed-ro')].map(e => e.textContent).join(' | '),
    edPaths: inputs.map(i => i.dataset.ed),
    imgCount: b.querySelectorAll('.ed-thumb img').length,
  };
});

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
  await page.goto(URL_PAGE, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    document.getElementById('email').value = 'ops@vorlina.net';
    document.getElementById('pw').value = 'whatever';
    document.getElementById('loginForm').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  });
  await page.waitForFunction(() => !document.getElementById('app').hidden && document.getElementById('view').textContent.length > 200, { timeout: 15000 });

  /* ═══ ① 栏目页：整页 → 顶层键各占一个分区 ═══ */
  section('栏目页 · 整页分区（factory）');
  await openEditor(page, 'pages', 'factory');
  let st = await edState(page);
  check('S1 分区数 = ' + EXPECT.factoryBlocks + '（顶层键扣掉内部隐藏的 pvbar）', st.secCount === EXPECT.factoryBlocks,
        '实际 ' + st.secCount + '：' + st.secTitles.join(' / '));
  check('S2 分区标题是中文（含「SEO 与分享卡片」「页头」）',
        st.secTitles.includes('SEO 与分享卡片') && st.secTitles.includes('页头'), st.secTitles.join(' / '));
  check('S3 真源字面量出现在编辑区（' + EXPECT.seoTitle.slice(0, 22) + '…）', st.text.includes(EXPECT.seoTitle));
  check('S4 内部字段 _note / _rules 已隐藏', !st.text.includes('_note') && !st.text.includes('_rules'));
  check('S5 预览条 pvbar 已隐藏（deny 生效）', !st.text.includes('pvbar'), st.text.slice(0, 120));
  check('S6 分区标题可折叠（点击后出现 folded）', await page.evaluate(() => {
    const h = document.querySelector('#edBody .edsec-h');
    h.click();
    return !!document.querySelector('#edBody .edsec.folded');
  }));

  /* ═══ ② 首页：单块编辑 → 一个分区平铺，不切成 12 个 ═══ */
  section('首页 · 单块编辑（hero）');
  await page.evaluate(() => document.getElementById('edClose').click());
  await openEditor(page, 'home', '首页 · hero');
  st = await edState(page);
  check('S7 首页单块只渲染 1 个分区（不把 12 个字段切成 12 区）', st.secCount === 1, '实际 ' + st.secCount);
  check('S8 分区标题是中文「首屏」', (st.secTitles[0] || '') === '首屏', st.secTitles[0]);
  check('S9 真源字面量（眉标 ' + EXPECT.heroKick + '）', st.text.includes(EXPECT.heroKick));
  check('S10 图片文件名给了中文标签（不裸奔 img）',
        st.text.includes('图片文件名') && st.edPaths.some(p => /\["hero","img"\]/.test(p)),
        st.edPaths.slice(0, 3).join(' '));

  /* ═══ ③ 文章：四分区 + slug 只读 + 配图预览 ═══ */
  section('文章 · 分区表单');
  await page.evaluate(() => document.getElementById('edClose').click());
  await openEditor(page, 'notes', '文章 · ');
  st = await edState(page);
  check('S11 四个分区（基本信息 / 只读 / 配图 / 正文块）', st.secCount === 4,
        '实际 ' + st.secCount + '：' + st.secTitles.join(' / '));
  check('S12 真源标题 ' + EXPECT.noteTitle.slice(0, 24) + '…', st.text.includes(EXPECT.noteTitle));
  check('S13 slug 只读（出现在 .ed-ro，不出现在可编辑路径里）',
        st.roText.includes(EXPECT.noteSlug) && !st.edPaths.some(p => /"slug"/.test(p)),
        'ro=' + st.roText.slice(0, 80) + ' paths=' + st.edPaths.filter(p => /slug/.test(p)).join(','));
  check('S14 配图有预览 img（' + EXPECT.noteImage + '）', st.imgCount >= 1, '实际 ' + st.imgCount);
  check('S15 内部字段 image 之外的尺寸标记不再平铺（cardW/cardH 不进白名单）',
        !st.edPaths.some(p => /cardW|cardH/.test(p)));

  /* ═══ ④ 分类：四分区 + 卡片图预览 + slug 只读 ═══ */
  section('分类 · 分区表单');
  await page.evaluate(() => document.getElementById('edClose').click());
  await openEditor(page, 'products', '分类 · ' + EXPECT.catSlug);
  st = await edState(page);
  check('S16 四个分区（首页分类卡 / 分类名与导语 / 卖点要点 / 只读）', st.secCount === 4,
        '实际 ' + st.secCount + '：' + st.secTitles.join(' / '));
  check('S17 真源分类中文名 ' + EXPECT.catZh, st.text.includes(EXPECT.catZh));
  check('S18 卡片图有预览 img（' + EXPECT.catImg + '）', st.imgCount >= 1, '实际 ' + st.imgCount);
  check('S19 slug 只读（不出现在可编辑路径里）',
        st.roText.includes(EXPECT.catSlug) && !st.edPaths.some(p => /"slug"/.test(p)),
        st.edPaths.filter(p => /slug/.test(p)).join(','));
  check('S20 要点可增删（bullets 是可编辑路径）', st.edPaths.some(p => /"bullets"/.test(p)));

  /* ═══ ⑤ 改一格真的写进草稿文档（不落库，只校验 ED.doc） ═══ */
  section('编辑生效');
  const wrote = await page.evaluate(() => {
    const el = document.querySelector('#edBody [data-ed*="\\"short\\""]');
    if (!el) return { ok: false, why: '找不到短名输入框' };
    el.value = '改后短名-测试';
    el.dispatchEvent(new Event('input', { bubbles: true }));
    return { ok: true, doc: (ED.doc.categories[ED.sub[1]] || {}).short };
  });
  check('S21 改输入框 → ED.doc 同步（' + (wrote.doc || wrote.why) + '）', wrote.ok && wrote.doc === '改后短名-测试',
        JSON.stringify(wrote));

  section('稳定性');
  check('S22 全程无 JS 异常', jsErrors.length === 0, jsErrors.slice(0, 3).join(' | '));

  await browser.close();
  console.log(out.join('\n'));
  console.log('\n通过 ' + pass + ' / ' + (pass + fail) + (fail ? '　❌ 失败 ' + fail : '　✅ 全绿'));
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('运行失败：', e); process.exit(2) });
