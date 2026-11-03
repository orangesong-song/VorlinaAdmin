/**
 * vorlina-admin · vadmin-022「新建文章」验收
 * 2026-11-03 · 无头 Chrome（puppeteer-core）
 *
 * 背景：文章页此前只能在现有 10 篇里点「改」，加一篇必须手改 JSON。
 * 新建时必须自动处理三件事，否则会制造错误：
 *   ① ix 编号递增（Note 11、12…）—— 撞号会让两篇在列表里看起来一样
 *   ② slug 生成 + 查重 —— 撞了就是两篇抢同一个 URL
 *   ③ 状态默认 draft —— 未写完的稿不能出现在站内列表
 *
 * 断言口径：
 *   · 角标必须是「按数据算出来的 10」，不是 NAV 里硬编码的 5
 *   · 新建后的 ix / slug / status 必须真的对
 *   · 保存时 PUT 的 payload 必须包含新文章且字段正确（不是只改了内存）
 */
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const SB = 'https://jjmaularjtmhptbfnovd.supabase.co';
const ORIGIN = 'http://127.0.0.1:8778';
const URL_PAGE = ORIGIN + '/index.html';
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const SITE = path.resolve(__dirname, '..', '..', 'vorlina-new');

const INS = JSON.parse(fs.readFileSync(path.join(SITE, 'build/data/insights.json'), 'utf8'));
const N0 = INS.notes.length;
const IX0 = INS.notes.reduce((m, n) => Math.max(m, parseInt((/(\d+)/.exec(n.ix || '') || [0, 0])[1], 10)), 0);

const NEW_TITLE = 'E2E Test Article';
const NEW_SLUG = 'e2e-test-article';
const EXPECT_IX = 'Note ' + String(IX0 + 1).padStart(2, '0');

/* overlay 里可能已有 insights.json（之前测试留下的），先备份，结束后还原 */
const OV = path.join(__dirname, '..', '.local-drafts', 'build', 'data', 'insights.json');
const OV_BAK = OV + '.e2e-bak';
const hadOverlay = fs.existsSync(OV);
if (hadOverlay) fs.copyFileSync(OV, OV_BAK);

let pass = 0, fail = 0;
const out = [];
function check(name, cond, detail) {
  if (cond) { pass++; out.push('  OK  ' + name); }
  else { fail++; out.push('  XX  ' + name + (detail ? '  -> ' + detail : '')); }
}
function section(t) { out.push('\n' + t); }

function mockSb(page) {
  page.on('request', req => {
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
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 2 });

  const jsErrors = [];
  page.on('console', m => {
    if (m.type() !== 'error') return;
    if (/Failed to load resource/.test(m.text())) return;
    jsErrors.push('console: ' + m.text());
  });
  page.on('pageerror', e => jsErrors.push('pageerror: ' + e.message));

  await page.setRequestInterception(true);

  /* 捕获保存时的 PUT payload（只读，不拦截 —— 让 mockSb 继续处理） */
  let put = null;   /* 解码后的 insights.json 文档 */
  page.on('request', req => {
    if (!(req.method() === 'PUT' && /\/content$/.test(req.url().split('?')[0]))) return;
    try {
      const envelope = JSON.parse(req.postData() || '{}');
      /* contentPut 发的是 { path, message, content: base64(JSON 文本) } */
      put = envelope.content
        ? JSON.parse(Buffer.from(envelope.content, 'base64').toString('utf8'))
        : null;
    } catch (e) { put = null; }
  });
  mockSb(page);

  await page.evaluateOnNewDocument(o => { try { localStorage.setItem('va_content_base', o) } catch (e) {} }, ORIGIN);
  /* prompt 直接返回标题，把「用户输入」这一步变成确定值 */
  await page.evaluateOnNewDocument(t => { window.prompt = () => t; }, NEW_TITLE);

  await page.goto(URL_PAGE, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    document.getElementById('email').value = 'ops@vorlina.net';
    document.getElementById('pw').value = 'whatever';
    document.getElementById('loginForm').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  });
  await page.waitForFunction(() => !document.getElementById('app').hidden && document.getElementById('view').textContent.length > 200, { timeout: 15000 });

  await page.evaluate(() => { location.hash = '#/notes' });
  await page.waitForFunction(() => document.querySelectorAll('#view table.tbl tbody tr').length > 0, { timeout: 10000 });

  /* ── K · 角标与入口 ── */
  section('K · 导航角标 + 新建入口');
  const k0 = await page.evaluate(() => {
    const b = document.querySelector('.rail-item[data-go="notes"] .badge');
    return { badge: b ? b.textContent.trim() : null, hasBtn: !!document.getElementById('noteNew'),
             rows: document.querySelectorAll('#view table.tbl tbody tr').length };
  });
  check('K0 导航「文章」角标 = 实际篇数 ' + N0 + '（不是硬编码的 5）',
    k0.badge === String(N0), '实际 ' + k0.badge);
  check('K1 文章页有「＋ 新建文章」按钮', k0.hasBtn);
  check('K2 列表行数 = ' + N0, k0.rows === N0, '实际 ' + k0.rows);

  /* ── N · 新建 → 编辑器 ── */
  section('N · 新建文章（ix / slug / status 自动）');
  await page.evaluate(() => document.getElementById('noteNew').click());
  await page.waitForFunction(() => !document.getElementById('edWrap').hidden, { timeout: 8000 });

  const n0 = await page.evaluate(() => ({
    title: document.getElementById('edTitle').textContent,
    body: document.getElementById('edBody').innerText,
    version: (document.body.innerText.match(/vadmin-0\d\d/) || [''])[0],
    blocks: document.querySelectorAll('#edBody [data-ed]').length,
  }));
  check('N1 编辑器已打开且标题含新文章名', n0.title.indexOf(NEW_TITLE) >= 0, n0.title.slice(0, 80));
  check('N2 编号自动递增到 ' + EXPECT_IX, n0.body.indexOf(EXPECT_IX) >= 0,
    '正文片段: ' + n0.body.replace(/\s+/g, ' ').slice(0, 120));
  check('N3 slug 由标题生成（' + NEW_SLUG + '）', n0.body.indexOf(NEW_SLUG) >= 0);
  check('N4 状态默认 draft', /\bdraft\b/.test(n0.body));
  check('N5 编辑器带版本戳 vadmin-022', n0.version.indexOf('vadmin-022') >= 0, n0.version.slice(0, 40));

  /* ── S · 保存到草稿 ── */
  section('S · 保存（PUT payload 必须包含新文章）');
  await page.evaluate(() => document.getElementById('edSave').click());
  await page.waitForFunction(() => /已保存|保存失败/.test(document.getElementById('edMsg').textContent), { timeout: 15000 });

  const s0 = await page.evaluate(() => document.getElementById('edMsg').textContent);
  check('S1 保存成功（无 401 / 无报错）', /已保存/.test(s0), s0.slice(0, 120));
  check('S2 提示里说明「draft 不会出现在列表」', /draft/.test(s0) && /published/.test(s0), s0.slice(0, 160));

  check('S3 PUT 已发出且 content 解码后可解析', !!put && !!put.notes, put ? 'notes=' + (put.notes || []).length : '未捕获');
  if (put && put.notes) {
    const last = put.notes[put.notes.length - 1];
    check('S4 payload 篇数 = ' + (N0 + 1), put.notes.length === N0 + 1, '实际 ' + put.notes.length);
    check('S5 新文章 ix = ' + EXPECT_IX, last.ix === EXPECT_IX, last.ix);
    check('S6 新文章 slug = ' + NEW_SLUG, last.slug === NEW_SLUG, last.slug);
    check('S7 新文章 status = draft', last.status === 'draft', last.status);
    check('S8 新文章 title 正确', last.title === NEW_TITLE, last.title);
    check('S9 正文块初始 2 块（h2 + p）', Array.isArray(last.blocks) && last.blocks.length === 2,
      JSON.stringify(last.blocks || []).slice(0, 80));
    check('S10 已有 10 篇未被改动', (() => {
      for (let i = 0; i < N0; i++) {
        if (put.notes[i].slug !== INS.notes[i].slug) return false;
        if (put.notes[i].title !== INS.notes[i].title) return false;
      }
      return true;
    })());
    fs.writeFileSync('/tmp/va-newnote-payload.json', JSON.stringify(put, null, 1));
    out.push('  （payload 已存 /tmp/va-newnote-payload.json，供构建级验证）');
  }

  await page.screenshot({ path: '/tmp/va-new-note.png' });
  check('Z1 无 JS 报错', jsErrors.length === 0, jsErrors.slice(0, 2).join(' | '));

  /* ── 清场：还原 overlay ── */
  try {
    if (hadOverlay) fs.copyFileSync(OV_BAK, OV), fs.unlinkSync(OV_BAK);
    else if (fs.existsSync(OV)) fs.unlinkSync(OV);
  } catch (e) {}

  await browser.close();

  console.log(out.join('\n'));
  console.log('\n' + '─'.repeat(56));
  console.log('结果：' + pass + ' 通过 / ' + fail + ' 失败');
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
