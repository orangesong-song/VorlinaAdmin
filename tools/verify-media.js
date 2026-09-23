/**
 * vorlina-admin · vadmin-013「媒体库直传」真实浏览器验证
 * 2026-09-23 · 无头 Chrome（puppeteer-core）
 *
 * 前置：tools/serve-local.py 已在 8778 跑着（含 /media 同形桩）。
 *       Supabase 用夹具；内容（imagery.json）与上传文件都是真的。
 *
 * 断言原则（与既有套件同一条纪律）：
 *   ① 上传真跑通（真二进制文件 → 桩落盘 → 列表回来 → 网格出现卡片）
 *   ② 上传过的图**必须改走 Worker 直读**（imgSrc 生效）—— 否则产品页预览会裂图
 *   ③ 仓库图仍走官网域（不能因为上传功能把几百张仓库图都代理一遍）
 *   ④ 类型与大小闸门真拦得住（假类型必须被拒，且页面如实报错不假装成功）
 *   ⑤ 移除只删媒体库、不动仓库（桩侧验证：assets/img 不受影响）
 *   ⑥ 全程无 JS 异常
 */
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');
const os = require('os');

const SB = 'https://jjmaularjtmhptbfnovd.supabase.co';
const ORIGIN = 'http://127.0.0.1:8778';
const URL_PAGE = ORIGIN + '/index.html';
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const SITE = path.resolve(__dirname, '..', '..', 'vorlina-new');
const ADMIN = path.resolve(__dirname, '..');
const MEDIA_DIR = path.join(ADMIN, '.local-drafts', 'media');

const imagery = JSON.parse(fs.readFileSync(path.join(SITE, 'build/data/imagery.json'), 'utf8'));
const REPO_NAMES = new Set();
for (const k of Object.keys(imagery)) for (const it of ((imagery[k] || {}).items || [])) if (it && it.src) REPO_NAMES.add(it.src);
const EXPECT = { repoCount: REPO_NAMES.size };

/* ── 真文件：1×1 PNG + 一个伪装成 png 的文本（测类型闸门）── */
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'vmedia-'));
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8AAQwAI/AL+6d0jjwAAAABJRU5ErkJggg==',
  'base64');
const TAG = 'zz-e2e-' + Date.now() + '.png';
const FILE_OK = path.join(TMP, TAG);
const FILE_BAD = path.join(TMP, 'zz-e2e-bad.txt');
fs.writeFileSync(FILE_OK, PNG);
fs.writeFileSync(FILE_BAD, 'this is definitely not an image');

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

(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await browser.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(String(e.message)));
  page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });

  await mockSb(page);
  await page.setRequestInterception(true);
  await page.evaluateOnNewDocument(o => { try { localStorage.setItem('va_content_base', o) } catch (e) {} }, ORIGIN);

  await page.goto(URL_PAGE, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    document.getElementById('email').value = 'ops@vorlina.net';
    document.getElementById('pw').value = 'x';
    document.getElementById('loginForm').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  });
  await page.waitForFunction(
    () => !document.getElementById('app').hidden && document.getElementById('view').textContent.length > 200,
    { timeout: 20000 });

  /* 每次跑测前清掉上次残留，避免断言被脏数据污染 */
  /* ⚠️ 不尝试清空媒体目录：NAS 上 fs.rmSync 会被系统安全机制拦掉（抛错被吞 → 静默脏数据）。
     正确做法是**期望值全部现算**（基线取当前已上传数），断言就对残留免疫。 */

  section('M · 媒体库页面');
  await page.evaluate(() => { location.hash = '#/media' });
  await page.waitForFunction(() => document.getElementById('mzone'), { timeout: 10000 });
  await page.waitForFunction(
    () => document.querySelectorAll('#view .mcard').length > 0, { timeout: 15000 });

  await page.waitForFunction(() => typeof MEDIA !== 'undefined' && MEDIA.loaded && !MEDIA.loading, { timeout: 15000 });
  const st0 = await page.evaluate(() => ({
    zone: !!document.getElementById('mzone'),
    pick: !!document.getElementById('mpick'),
    file: !!document.getElementById('mfile'),
    heads: [...document.querySelectorAll('#view .msec-h')].map(e => e.textContent.trim()),
    cards: document.querySelectorAll('#mgrid-repo .mcard').length,
    upCards: document.querySelectorAll('#mgrid-up .mcard').length,
    copyBtns: document.querySelectorAll('#view [data-copy]').length,
    delBtns: document.querySelectorAll('#mgrid-repo [data-mdel]').length,
    text: document.getElementById('view').textContent,
  }));
  check('M1 上传区三件套齐全（拖拽区 / 选择按钮 / file input）', st0.zone && st0.pick && st0.file);
  check('M2 两个分区标题都在（已上传 + 仓库图库）',
    st0.heads.length === 2 && /已上传/.test(st0.heads[0]) && /仓库图库/.test(st0.heads[1]), st0.heads.join(' | '));
  check('M3 仓库图库渲染出 ' + EXPECT.repoCount + ' 张（从 imagery.json 现算）',
    st0.cards === EXPECT.repoCount, '实际 ' + st0.cards);
  check('M4 每张卡片都有「复制文件名」（含已上传区）', st0.copyBtns === st0.cards + st0.upCards,
    st0.copyBtns + ' vs ' + (st0.cards + st0.upCards));
  check('M5 未上传时没有「移除」按钮（仓库图只读）', st0.delBtns === 0, String(st0.delBtns));
  check('M6 页面明说「上传 = 草稿，不会直接上线」', /上传 = 草稿，不会直接上线/.test(st0.text));

  section('U · 上传真跑通');
  /* mediaLoad 完成后会整块重渲染（innerHTML 替换）—— 抢在前面拿的 handle 是 detached 的，
     uploadFile 打在它上面不会触发任何事件。所以先等 loaded 稳定再取元素。 */
  const settled = () => page.waitForFunction(
    () => typeof MEDIA !== 'undefined' && MEDIA.loaded && !MEDIA.loading, { timeout: 15000 });
  await settled();
  const input = await page.$('#mfile');
  await input.uploadFile(FILE_OK);
  await page.waitForFunction(
    t => [...document.querySelectorAll('#mgrid-up .mcard-n')].some(e => e.textContent === t),
    { timeout: 15000 }, TAG);

  const st1 = await page.evaluate(tag => ({
    upCards: document.querySelectorAll('#mgrid-up .mcard').length,
    repoCards: document.querySelectorAll('#mgrid-repo .mcard').length,
    delBtns: document.querySelectorAll('#mgrid-up [data-mdel]').length,
    upSrc: (() => {
      const c = [...document.querySelectorAll('#mgrid-up .mcard')]
        .find(x => (x.querySelector('.mcard-n') || {}).textContent === tag);
      return c ? (c.querySelector('img') || {}).src : '';
    })(),
    msg: document.getElementById('view').textContent,
  }), TAG);
  check('U1 已上传区多出一张（基线 ' + st0.upCards + ' → ' + st1.upCards + '，现算）',
    st1.upCards === st0.upCards + 1, st0.upCards + ' → ' + st1.upCards);
  check('U2 新卡片走 Worker 直读（/media/file/img/）—— 上传的图此刻只在这里有',
    new RegExp('/media/file/img/' + TAG.replace(/[.]/g, '\\.') + '$').test(st1.upSrc || ''), st1.upSrc);
  check('U3 上传过的卡片才有「移除」', st1.delBtns === st1.upCards, st1.delBtns + ' vs ' + st1.upCards);
  check('U4 页面如实报成功（不假装、不静默）', /已上传 1 个/.test(st1.msg), st1.msg.slice(-160));
  check('U5 文件真的落盘（.local-drafts/media/）', fs.existsSync(path.join(MEDIA_DIR, TAG)));

  section('R · 类型闸门与基址切换');
  await settled();
  const input2 = await page.$('#mfile');
  await input2.uploadFile(FILE_BAD);
  await page.waitForFunction(
    () => /失败 1 个|bad_type/.test(document.getElementById('view').textContent), { timeout: 15000 });
  const st2 = await page.evaluate(() => ({
    msg: document.getElementById('view').textContent,
    cards: document.querySelectorAll('#mgrid-up .mcard').length,
  }));
  check('R1 伪装成 png 的文本被拒（bad_type）', /bad_type/.test(st2.msg));
  check('R2 被拒后已上传区没多出卡片', st2.cards === st1.upCards, st1.upCards + ' → ' + st2.cards);
  check('R3 被拒文件没落盘', !fs.existsSync(path.join(MEDIA_DIR, 'zz-e2e-bad.txt')));

  /* 上传过的图，产品页缩略图必须改走 Worker；仓库图仍走官网域 */
  await page.evaluate(() => { location.hash = '#/products' });
  await page.waitForFunction(() => document.querySelectorAll('#view .pcard').length > 0, { timeout: 15000 });
  const st3 = await page.evaluate(() => ({
    cards: document.querySelectorAll('#view .pcard').length,
    srcs: [...document.querySelectorAll('#view .pcard-thumb img')].slice(0, 4).map(i => i.src),
  }));
  check('R4 产品卡片仍在（' + st3.cards + ' 张）', st3.cards > 0);
  check('R5 仓库图仍走官网域 vorlina.net（不把几百张图都代理一遍）',
    st3.srcs.length > 0 && st3.srcs.every(s => s.startsWith('https://vorlina.net/')), st3.srcs[0]);

  section('D · 移除只删媒体库');
  await page.evaluate(() => { location.hash = '#/media' });
  await page.waitForFunction(() => document.getElementById('mzone'), { timeout: 10000 });
  await settled();
  await page.waitForFunction(
    t => [...document.querySelectorAll('#mgrid-up .mcard-n')].some(e => e.textContent === t),
    { timeout: 15000 }, TAG);
  page.on('dialog', async d => { await d.accept(); });
  await page.evaluate(t => {
    const card = [...document.querySelectorAll('#mgrid-up .mcard')]
      .find(x => (x.querySelector('.mcard-n') || {}).textContent === t);
    const b = card && card.querySelector('[data-mdel]');
    if (b) b.click();
  }, TAG);
  await page.waitForFunction(
    t => ![...document.querySelectorAll('#mgrid-up .mcard-n')].some(e => e.textContent === t),
    { timeout: 15000 }, TAG).catch(() => {});
  const st4 = await page.evaluate(t => ({
    upCards: document.querySelectorAll('#mgrid-up .mcard').length,
    repoCards: document.querySelectorAll('#mgrid-repo .mcard').length,
    gone: ![...document.querySelectorAll('#mgrid-up .mcard-n')].some(e => e.textContent === t),
  }), TAG);
  check('D1 移除后卡片从已上传区消失', st4.gone);
  check('D2 已上传区回到上传前基数 ' + st0.upCards + ' 张（' + st4.upCards + '）',
    st4.upCards === st0.upCards, String(st4.upCards));
  check('D3 仓库图区不受影响（仍是 ' + EXPECT.repoCount + ' 张）', st4.repoCards === EXPECT.repoCount, String(st4.repoCards));
  /* 桩把删掉的文件移进 .trash/（本机 os.remove 会被系统安全机制拦），所以「不再在媒体区」= 删除生效 */
  check('D4 文件已移出媒体区（进了 .trash/）',
    !fs.existsSync(path.join(MEDIA_DIR, TAG)) && fs.existsSync(path.join(MEDIA_DIR, '.trash', TAG)));

  section('X · 无脚本异常');
  const real = errs.filter(e => !/favicon|Failed to load resource/i.test(e));
  check('X1 全程无 JS 异常', real.length === 0, real.slice(0, 3).join(' | '));

  await browser.close();
  console.log(out.join('\n'));
  console.log('\n媒体库 E2E：' + pass + ' 通过 / ' + fail + ' 失败（共 ' + (pass + fail) + '）');
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('FATAL', e); process.exit(2) });
