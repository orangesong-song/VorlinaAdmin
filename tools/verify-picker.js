/**
 * vorlina-admin · vadmin-017「选图弹层 + PUT 鉴权修复」真实浏览器验证
 * 2026-09-23 · 无头 Chrome（puppeteer-core）
 *
 * 背景（线上实锤的两个问题）：
 *   ① 「保存草稿」报 401 missing_token —— contentFetch 用 Object.assign({headers:A}, opts)，
 *      PUT 自带的 Content-Type 把 Authorization 整个覆盖掉（读得到、存不了）。
 *   ② 运营换图要去媒体库复制文件名再回来粘贴 —— 反人类。vadmin-017 加「选图」弹层：
 *      点图即填 + 弹层内可直接上传。
 *
 * vadmin-018 增补：弹层内「上传新图」必须有可见反馈
 *   （此前上传结果只写 MEDIA.msg，产品编辑页里 rerenderMedia 直接 return
 *     —— 成功失败都无动静，用户以为「没有上传新图」）。
 *
 * 断言原则：真源字面量、交互真生效、请求头真的带上了。
 */
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const SB = 'https://jjmaularjtmhptbfnovd.supabase.co';
const ORIGIN = 'http://127.0.0.1:8778';
const URL_PAGE = ORIGIN + '/index.html';
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const SITE = path.resolve(__dirname, '..', '..', 'vorlina-new');

const prod = JSON.parse(fs.readFileSync(path.join(SITE, 'data/products.json'), 'utf8'));
const P0 = prod.products[0];
const EXPECT = { usable0: P0.images.usable[0], usableN: P0.images.usable.length };
const SHOT = path.join(__dirname, '..', '_not-for-site', '验收截图-20260923', '30-选图弹层.png');

/* 自备夹具：往本地「R2 桶」放一张真·1×1 PNG（不是 8 字节垃圾字节 —— 垃圾图
   永远解不出来，断言就变成废的）。用例自己创建、自己清理，不靠别人遗留。 */
const MEDIA_DIR = path.join(__dirname, '..', '.local-drafts', 'media');
const FIXTURE = 'e2e-常驻探针-1x1.png';
const PNG_1X1 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=';
fs.mkdirSync(MEDIA_DIR, { recursive: true });
fs.writeFileSync(path.join(MEDIA_DIR, FIXTURE), Buffer.from(PNG_1X1, 'base64'));

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
    if (/Failed to load resource/.test(m.text())) return;
    jsErrors.push('console: ' + m.text());
  });
  await page.setRequestInterception(true);
  mockSb(page);
  await page.evaluateOnNewDocument(o => { try { localStorage.setItem('va_content_base', o) } catch(e){} }, ORIGIN);
  await page.goto(URL_PAGE, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    document.getElementById('email').value = 'ops@vorlina.net';
    document.getElementById('pw').value = 'whatever';
    document.getElementById('loginForm').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  });
  await page.waitForFunction(() => !document.getElementById('app').hidden && document.getElementById('view').textContent.length > 200, { timeout: 15000 });

  /* 打开首款编辑器 */
  await page.evaluate(() => { location.hash = '#/products' });
  await page.waitForFunction(() => document.querySelectorAll('#view .pcard').length > 0, { timeout: 10000 });
  await page.evaluate(() => document.querySelector('#view .pcard [data-opened]').click());
  await page.waitForFunction(() => !document.getElementById('edWrap').hidden, { timeout: 8000 });

  /* ── P · 选图按钮 ── */
  section('P · 图片字段的「选图」按钮');
  const p0 = await page.evaluate(() => ({
    pickBtns: document.querySelectorAll('#edBody [data-pick]').length,
    usableInputs: [...document.querySelectorAll('#edBody [data-ed]')]
      .filter(x => /"usable"/.test(x.dataset.ed)).length,
    wrapped: document.querySelectorAll('#edBody .ed-pickrow').length,
  }));
  check('P1 图片字段旁有「选图」按钮（画廊 ' + EXPECT.usableN + ' 格每格一个）',
    p0.pickBtns >= EXPECT.usableN, '实际 ' + p0.pickBtns);
  check('P2 输入框与按钮同行包裹（不破版式）', p0.wrapped >= EXPECT.usableN, '实际 ' + p0.wrapped);

  /* ── U · 弹层打开与内容 ── */
  section('U · 选图弹层');
  await page.evaluate(() => document.querySelector('#edBody [data-pick]').click());
  await page.waitForFunction(() => !document.getElementById('pickPanel').hidden, { timeout: 8000 });
  await page.waitForFunction(() => document.querySelectorAll('#pickBody .pick-item').length > 0, { timeout: 15000 });
  const u0 = await page.evaluate(e0 => {
    const items = [...document.querySelectorAll('#pickBody .pick-item')];
    return {
      n: items.length,
      withImg: items.filter(x => (x.querySelector('img') || {}).src).length,
      uploaded: items.filter(x => /\/media\/file\/img\//.test((x.querySelector('img') || {}).src || '')).length,
      hasUpload: !!document.getElementById('pickFile'),
      targetExists: items.some(x => x.dataset.pickitem === e0),
    };
  }, EXPECT.usable0);
  /* 夹具图的缩略图必须真的解码出来 —— 只查 src 会漏掉「路径没解码 / 回源 404」这类裂图 */
  const fixThumb = await page.evaluate(async name => {
    const el = [...document.querySelectorAll('#pickBody .pick-item')].find(x => x.dataset.pickitem === name);
    if (!el) return { found: false };
    const img = el.querySelector('img');
    const t0 = Date.now();
    while (!(img.complete && img.naturalWidth > 0) && Date.now() - t0 < 6000) await new Promise(r => setTimeout(r, 100));
    return { found: true, w: img.naturalWidth, src: img.src };
  }, FIXTURE);
  check('U1 弹层弹出且图库非空（' + u0.n + ' 张）', u0.n > 5, '实际 ' + u0.n);
  check('U2 每张都有缩略图', u0.withImg === u0.n, u0.withImg + ' / ' + u0.n);
  check('U3 弹层内可直接上传（不用跑去媒体库）', u0.hasUpload);
  check('U4 真源画廊图 ' + EXPECT.usable0 + ' 在列表里（仓库图 + 已上传合并去重）', u0.targetExists);
  check('U5 已上传的图走 Worker 直读（src 前缀 /media/file/img/）',
    u0.uploaded > 0 && /\/media\/file\/img\//.test(fixThumb.src || ''), '上传区 ' + u0.uploaded + ' 张 · src=' + (fixThumb.src || ''));
  check('U6 已上传图的缩略图真能显示（naturalWidth>0 —— 只查 src 会漏 URL 编码/回源 404 类裂图）',
    fixThumb.found && fixThumb.w > 0, JSON.stringify(fixThumb));
  /* 截图前等 lazy 图解码完 —— 否则截出来全是空块（2026-09-23 教训：别拿假象当 bug） */
  await page.evaluate(() => {
    return Promise.all([...document.querySelectorAll('#pickBody .pick-item img')].map(img =>
      (img.complete && img.naturalWidth > 0) ? Promise.resolve()
        : new Promise(r => { img.addEventListener('load', r, { once: true }); img.addEventListener('error', r, { once: true }); })
    ));
  }).catch(() => {});
  await new Promise(r => setTimeout(r, 800));
  await page.screenshot({ path: SHOT });
  out.push('  （截图 → ' + path.basename(SHOT) + '）');

  /* ── PL · 弹层内上传要有反馈（vadmin-018）────────────────
     页面内包一层 fetch 延迟 600ms，制造确定的 busy 窗口；
     上传走本地 stub 真落盘，断言完删掉清场。 */
  section('PL · 弹层内上传反馈（vadmin-018）');
  await page.evaluate(() => {
    window._origFetch = window.fetch;
    window.fetch = (url, opts) => /\/media\/upload$/.test(String(url))
      ? new Promise(r => setTimeout(() => r(window._origFetch(url, opts)), 600))
      : window._origFetch(url, opts);
  });
  /* 文件名带时间戳：每次唯一 —— 否则前一次残留会让「等它出现」假通过（2026-09-23 实测翻车） */
  const UP_NAME = 'e2e-' + Date.now() + '-上传反馈测试.png';
  const preHas = await page.evaluate(name => [...document.querySelectorAll('#pickBody .pick-item')]
    .some(x => x.dataset.pickitem === name), UP_NAME);
  check('PL0 前置：本次测试文件名此前不在列表里（不然 PL2 会假通过）', !preHas);
  await page.evaluate(name => {
    const dt = new DataTransfer();
    dt.items.add(new File([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])], name, { type: 'image/png' }));
    const inp = document.getElementById('pickFile');
    inp.files = dt.files;
    inp.dispatchEvent(new Event('change', { bubbles: true }));
  }, UP_NAME);
  const busyTxt = await page.evaluate(() => {
    const n = document.querySelector('#pickBody .notice');
    return n ? n.textContent : '';
  });
  check('PL1 点完文件立刻出现「正在上传」横幅（不再毫无反应）', /正在上传/.test(busyTxt), '实际：' + busyTxt);
  const itemSeen = await page.waitForFunction(name => [...document.querySelectorAll('#pickBody .pick-item')]
    .some(x => x.dataset.pickitem === name), { timeout: 10000 }, UP_NAME).then(() => true).catch(() => false);
  const doneTxt = await page.evaluate(() => {
    const n = document.querySelector('#pickBody .notice.safe');
    return n ? n.textContent : '';
  });
  check('PL2 上传完成后新图真的出现在弹层列表（点一下就能填）', itemSeen);
  check('PL3 显示结果横幅（已上传 ' + UP_NAME + '）', /已上传 1 个/.test(doneTxt) && doneTxt.indexOf(UP_NAME) >= 0, '实际：' + doneTxt);
  /* 清场必须断言 —— 之前被 .catch 吞掉，垃圾文件静默累积（图库 57→58） */
  const delRes = await page.evaluate(async name => {
    const res = await fetch(CONTENT_BASE + '/media/file/img/' + encodeURIComponent(name),
      { method: 'DELETE', headers: { Authorization: 'Bearer ' + sbToken() } });
    const j = await res.json().catch(() => ({}));
    return { ok: !!(j && j.ok), status: res.status, err: (j && j.error) || '' };
  }, UP_NAME).catch(e => ({ ok: false, status: 0, err: String(e && e.message) }));
  const stillThere = await page.evaluate(async name => {
    window.fetch = window._origFetch;                 /* 恢复原 fetch，别影响后续断言 */
    await mediaLoad();
    renderPickGrid();
    return (MEDIA.items || []).some(it => it.name === name);
  }, UP_NAME);
  check('PL4 清场：测试文件已从本地图库移除（不留垃圾、不污染后续断言）',
    delRes.ok && !stillThere, 'delete=' + JSON.stringify(delRes) + ' still=' + stillThere);
  await new Promise(r => setTimeout(r, 400));

  /* ── S · 点图填入 ── */
  section('S · 点图填入');
  const pickName = await page.evaluate(e0 => {
    const it = [...document.querySelectorAll('#pickBody .pick-item')]
      .find(x => x.dataset.pickitem === e0) || document.querySelector('#pickBody .pick-item');
    const name = it.dataset.pickitem;
    it.click();
    return name;
  }, EXPECT.usable0);
  await new Promise(r => setTimeout(r, 300));
  const s0 = await page.evaluate(name => {
    const el = [...document.querySelectorAll('#edBody [data-ed]')]
      .find(x => /"usable"/.test(x.dataset.ed) && x.tagName === 'INPUT');
    return {
      closed: document.getElementById('pickPanel').hidden,
      firstUsable: el ? el.value : '',
      docVal: (function () {
        try { return edGet(ED.doc, JSON.parse(el.dataset.ed)) } catch (e) { return null }
      })(),
    };
  }, pickName);
  check('S1 点图后弹层自动关闭', s0.closed);
  check('S2 输入框真的变成点选的文件名（' + pickName + '）', s0.firstUsable === pickName, '实际 ' + s0.firstUsable);
  check('S3 草稿对象同步更新（不只改了皮）', s0.docVal === pickName, '实际 ' + s0.docVal);

  /* ── N · ⑤ 图片分区的直传入口（vadmin-019）──────────────── */
  section('N · ⑤ 图片分区的直传入口（vadmin-019）');
  const n0 = await page.evaluate(() => ({
    ver: (document.querySelector('#edWrap .ed-head') || {}).textContent || '',
    heroPick: [...document.querySelectorAll('#edBody [data-pick]')]
      .some(b => /"images","hero"/.test(b.dataset.pick || '')),
    addBtn: !!document.querySelector('#edBody [data-pick="null"]'),
    usableN: (function () { try { return edGet(ED.doc, ED.sub.concat(['images','usable'])).length } catch (e) { return -1 } })(),
  }));
  check('N1 编辑弹窗头带版本戳 vadmin-019（一眼分清旧缓存 / 新 bug）', n0.ver.indexOf('vadmin-019') >= 0, n0.ver.slice(0, 60));
  check('N2 主图行有「选图」按钮', n0.heroPick);
  check('N3 分区有「上传新图 / 从图库追加」入口', n0.addBtn);
  await page.evaluate(() => document.querySelector('#edBody [data-pick="null"]').click());
  await page.waitForFunction(() => !document.getElementById('pickPanel').hidden, { timeout: 8000 });
  await page.waitForFunction(() => document.querySelectorAll('#pickBody .pick-item').length > 0, { timeout: 15000 });
  const addName = await page.evaluate(() => {
    let u = [];
    try { u = edGet(ED.doc, ED.sub.concat(['images','usable'])) || [] } catch (e) {}
    const it = [...document.querySelectorAll('#pickBody .pick-item')]
      .find(x => u.indexOf(x.dataset.pickitem) < 0);          /* 挑一个不在画廊里的，保证是真追加 */
    if (!it) return null;
    it.click();
    return it.dataset.pickitem;
  });
  await new Promise(r => setTimeout(r, 300));
  const n1 = await page.evaluate(name => {
    const u = edGet(ED.doc, ED.sub.concat(['images','usable'])) || [];
    return { closed: document.getElementById('pickPanel').hidden, n: u.length, has: u.indexOf(name) >= 0 };
  }, addName);
  check('N4 点图后弹层关闭且真追加进画廊（' + n0.usableN + ' → ' + n1.n + '，' + addName + '）',
    !!addName && n1.closed && n1.n === n0.usableN + 1 && n1.has, 'usable=' + n1.n + ' closed=' + n1.closed);

  /* ── H · PUT 请求必须带 Authorization（vadmin-017 头合并修复）── */
  section('H · 保存草稿的请求头');
  const auth = await page.evaluate(async () => {
    let seen = null;
    const orig = window.fetch;
    window.fetch = (url, opts) => {
      if (/\/content$/.test(String(url)) && opts && opts.method === 'PUT')
        seen = (opts.headers && opts.headers.Authorization) || null;
      return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    };
    try { await contentPut('data/__e2e__.json', { a: 1 }, 'e2e-header-探针'); } catch (e) {}
    window.fetch = orig;
    return seen;
  });
  check('H1 PUT /content 带 Authorization（修复前被 Content-Type 覆盖 → 401）',
    /Bearer\s+\S+/.test(auth || ''), '实际 ' + JSON.stringify(auth));

  check('Z1 全程无 JS 异常', jsErrors.length === 0, jsErrors.slice(0, 3).join(' | '));

  /* 夹具清场（本地桶，直接删文件；媒体路由的删已由 PL4 覆盖） */
  try { fs.unlinkSync(path.join(MEDIA_DIR, FIXTURE)) } catch (e) {}

  await browser.close();
  console.log(out.join('\n'));
  console.log('\n' + '='.repeat(52));
  console.log('通过 ' + pass + ' / 失败 ' + fail);
  console.log('='.repeat(52));
  if (jsErrors.length) console.log('JS 异常明细：\n' + jsErrors.join('\n'));
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('验证脚本自身出错：', e); process.exit(2); });
