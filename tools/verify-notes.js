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
    version: (document.body.innerText.match(/vadmin-\d{3}/) || [''])[0],
    blocks: document.querySelectorAll('#edBody [data-ed]').length,
  }));
  check('N1 编辑器已打开且标题含新文章名', n0.title.indexOf(NEW_TITLE) >= 0, n0.title.slice(0, 80));
  check('N2 编号自动递增到 ' + EXPECT_IX, n0.body.indexOf(EXPECT_IX) >= 0,
    '正文片段: ' + n0.body.replace(/\s+/g, ' ').slice(0, 120));
  check('N3 slug 由标题生成（' + NEW_SLUG + '）', n0.body.indexOf(NEW_SLUG) >= 0);
  check('N4 状态默认 draft', /\bdraft\b/.test(n0.body));
  check('N5 编辑器带版本戳（vadmin-NNN）', /^vadmin-\d{3}$/.test(n0.version), n0.version.slice(0, 40));

  /* ── V · 版本号可见 + 与站点版本串区分（vadmin-023）── */
  section('V · 后台版本号可见（侧栏 / 弹窗 / 总览三处一致）');
  const v0 = await page.evaluate(() => {
    const rail = document.querySelector('.rail-ver');
    const dlg = document.getElementById('edVer');
    return {
      rail: rail ? rail.textContent.replace(/\s+/g, ' ').trim() : '',
      dialog: dlg ? dlg.textContent.trim() : '',
      siteVer: (typeof STORE !== 'undefined' && STORE.version) ? String(STORE.version) : '',
    };
  });
  check('V1 侧栏底部常驻显示后台版本（不再只藏在弹窗里）', /vadmin-\d{3}/.test(v0.rail), v0.rail);
  check('V2 弹窗头版本戳与侧栏同源一致', v0.dialog === (v0.rail.match(/vadmin-\d{3}/) || [''])[0],
    '弹窗=' + v0.dialog + ' 侧栏=' + v0.rail);
  check('V3 站点版本串（20xxxxxx）与后台版本（vadmin-）是两个不同前缀',
    /^20\d{6}[a-z]$/.test(v0.siteVer) && /^vadmin-\d{3}$/.test(v0.dialog),
    '站点=' + v0.siteVer + ' 后台=' + v0.dialog);

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

  /* ── B · 正文块平铺：不再套娃（vadmin-023）─────────────────
     改动前：块 → 对象 → v → rows → 行 → 单元格，每层各画一个框；
     断言口径不是"看起来好看"，而是**块内不允许再出现通用渲染器的框**，
     以及加块 / 加行 / 加列 / 全部收起这些操作真的改了数据。 */
  section('B · 正文块平铺（一个块一个框）');
  const b0 = await page.evaluate(() => {
    const body = document.getElementById('edBody');
    const nb = [...body.querySelectorAll('.nb')];
    return {
      blocks: nb.length,
      nested: body.querySelectorAll('.nb .ed-obj, .nb .ed-item, .nb .ed-obj-h, .nb .ed-item-h').length,
      heads: nb.map(x => x.querySelector('.nb-h').innerText.replace(/\s+/g, ' ').trim()),
      types: nb.map(x => x.querySelector('.nb-t').textContent.trim()),
      hasPreview: nb.map(x => (x.querySelector('.nb-pv') || {}).textContent || ''),
      addBtns: [...body.querySelectorAll('[data-nbadd]')].map(e => e.dataset.nbadd),
      foldAll: !!body.querySelector('[data-nbfoldall="1"]'),
      overflow: body.scrollWidth - body.clientWidth,
    };
  });
  check('B1 正文块数量正确（新建文章默认 2 块）', b0.blocks === 2, '实际 ' + b0.blocks);
  check('B2 块内嵌套框已清零（ed-obj / ed-item 一律不出现）', b0.nested === 0, '残留 ' + b0.nested);
  check('B3 块标题行 = 块号 + 类型 + 摘要', /^块 1/.test(b0.heads[0]) && b0.types[0] === '标题' && b0.types[1] === '段落',
    b0.heads.join(' | '));
  b0.heads.forEach((h, i) => out.push('     ' + h));
  check('B4 六种块类型都有加块入口', b0.addBtns.join(',') === 'h2,p,ul,ol,table,notice', b0.addBtns.join(','));
  check('B5 有「全部收起」按钮（长文当目录看）', b0.foldAll);
  check('B6 无横向溢出（1020px 弹窗内表格能并排）', b0.overflow <= 0, b0.overflow + 'px');

  const bAdd = await page.evaluate(() => {
    const body = document.getElementById('edBody');
    body.querySelector('[data-nbadd="table"]').click();
    const nb = [...body.querySelectorAll('.nb')];
    const last = nb[nb.length - 1];
    return {
      n: nb.length,
      type: last.querySelector('.nb-t').textContent.trim(),
      rows: last.querySelectorAll('.nb-row:not(.nb-head)').length,
      cols: last.querySelectorAll('.nb-head .nb-cell').length,
      cellsAreTextarea: last.querySelectorAll('.nb-cells textarea').length,
    };
  });
  check('B7 加「表格」块后块数 3、初始 2 行 2 列',
    bAdd.n === 3 && bAdd.rows === 2 && bAdd.cols === 2, JSON.stringify(bAdd));
  check('B8 单元格与表头都是可换行 textarea（长句不被截断）',
    bAdd.cellsAreTextarea === bAdd.cols + bAdd.rows * bAdd.cols,
    '实际 ' + bAdd.cellsAreTextarea + '（表头 ' + bAdd.cols + ' + 数据 ' + (bAdd.rows * bAdd.cols) + '）');

  const bOp = await page.evaluate(() => {
    const body = document.getElementById('edBody');
    const last = () => { const nb = [...body.querySelectorAll('.nb')]; return nb[nb.length - 1] };
    last().querySelector('[data-nbcol="add"]').click();
    const cols1 = last().querySelectorAll('.nb-head .nb-cell').length;
    const cols1rows = last().querySelectorAll('.nb-row:not(.nb-head) .nb-cell').length / 2;
    last().querySelector('[data-nbrow="add"]').click();
    const rows1 = last().querySelectorAll('.nb-row:not(.nb-head)').length;
    return { cols1, cols1rows, rows1 };
  });
  check('B9 加列：表头 3 列，且每行同步加一格', bOp.cols1 === 3 && bOp.cols1rows === 3,
    '列=' + bOp.cols1 + ' 每行列数=' + bOp.cols1rows);
  check('B10 加行：3 行', bOp.rows1 === 3, '实际 ' + bOp.rows1);

  const bFold = await page.evaluate(() => {
    const body = document.getElementById('edBody');
    body.querySelector('[data-nbfoldall="1"]').click();
    const folded = body.querySelectorAll('.nb.folded').length;
    const total = body.querySelectorAll('.nb').length;
    const bodyHidden = getComputedStyle(body.querySelector('.nb .nb-b')).display === 'none';
    body.querySelector('[data-nbfoldall="0"]').click();
    const after = body.querySelectorAll('.nb.folded').length;
    return { folded, total, bodyHidden, after };
  });
  check('B11 全部收起：每块都折叠且内容区真的隐藏',
    bFold.folded === bFold.total && bFold.bodyHidden, JSON.stringify(bFold));
  check('B12 全部展开：折叠状态清零', bFold.after === 0, '剩余 ' + bFold.after);

  await page.screenshot({ path: '/tmp/va-new-note.png' });
  check('Z1 无 JS 报错', jsErrors.length === 0, jsErrors.slice(0, 2).join(' | '));

  /* ── 清场：还原 overlay ──
     ⚠️ NAS（smbfs）上 unlink 可能失败，而 catch 吞掉会让 **11 篇的测试副本留在 overlay**，
     下一次跑 verify-content 就会因为「文章 11 行」报红（2026-11-03 实际踩过）。
     ⇒ 删不掉就**覆盖回真源**：文件还在，但内容与仓库一致，不再污染后续断言。 */
  try {
    if (hadOverlay) fs.copyFileSync(OV_BAK, OV), fs.unlinkSync(OV_BAK);
    else if (fs.existsSync(OV)) fs.unlinkSync(OV);
  } catch (e) {
    try {
      fs.mkdirSync(path.dirname(OV), { recursive: true });
      fs.copyFileSync(path.join(SITE, 'build/data/insights.json'), OV);
      out.push('  !! overlay 删除失败，已覆盖回真源（' + e.code + '）');
    } catch (e2) {
      out.push('  !! overlay 清理失败且无法覆盖：' + e2.code + ' —— 下次跑测试前请手工清 .local-drafts/');
    }
  }
  if (fs.existsSync(OV)) {
    try {
      const left = JSON.parse(fs.readFileSync(OV, 'utf8'));
      const same = left.notes && left.notes.length === INS.notes.length;
      check('Z2 overlay 已清场（篇数回到 ' + INS.notes.length + '，不留测试文章）', same,
        '残留 ' + (left.notes || []).length + ' 篇：' + ((left.notes || [])[left.notes.length - 1] || {}).slug);
    } catch (e) { check('Z2 overlay 已清场', false, 'overlay 仍在且无法解析'); }
  }

  await browser.close();

  console.log(out.join('\n'));
  console.log('\n' + '─'.repeat(56));
  console.log('结果：' + pass + ' 通过 / ' + fail + ' 失败');
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
