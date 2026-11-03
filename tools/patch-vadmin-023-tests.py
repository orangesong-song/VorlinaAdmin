# -*- coding: utf-8 -*-
"""verify-notes.js 增补 vadmin-023 断言 + 版本号断言动态化。

要求：
1. 版本戳断言不能再写死 'vadmin-0XX'（上次写死 022，这次升 023 就红）——
   改为匹配 /vadmin-\\d{3}/ 且「弹窗头 == 侧栏底部」，并检查总览里写明了两者的区别。
2. 正文块平铺是本次改动的核心，必须有断言：
   块内不得再有 .ed-obj/.ed-item（套娃）；加块/加行/加列/全部收起都要真的生效。
"""
import io

F = 'tools/verify-notes.js'
s = io.open(F, encoding='utf-8').read()


def rep(old, new, why=''):
    global s
    c = s.count(old)
    assert c == 1, '锚点命中 %d 次（期望 1）%s: %r' % (c, why, old[:70])
    s = s.replace(old, new, 1)


# ── ① 版本断言动态化 ────────────────────────────────────────
rep("""    version: (document.body.innerText.match(/vadmin-0\\d\\d/) || [''])[0],""",
    """    version: (document.body.innerText.match(/vadmin-\\d{3}/) || [''])[0],""",
    '版本正则')

rep("""  check('N5 编辑器带版本戳 vadmin-022', n0.version.indexOf('vadmin-022') >= 0, n0.version.slice(0, 40));""",
    """  check('N5 编辑器带版本戳（vadmin-NNN）', /^vadmin-\\d{3}$/.test(n0.version), n0.version.slice(0, 40));""",
    'N5 断言')

# ── ② 新增 V · 版本号可见（用户"找不到版本戳"的直接回归）──
rep("""  /* ── S · 保存到草稿 ── */""",
    """  /* ── V · 版本号可见 + 与站点版本串区分（vadmin-023）── */
  section('V · 后台版本号可见（侧栏 / 弹窗 / 总览三处一致）');
  const v0 = await page.evaluate(() => {
    const rail = document.querySelector('.rail-ver');
    const dlg = document.getElementById('edVer');
    return {
      rail: rail ? rail.textContent.replace(/\\s+/g, ' ').trim() : '',
      dialog: dlg ? dlg.textContent.trim() : '',
      siteVer: (document.body.innerText.match(/\\b20\\d{6}[a-z]\\b/) || [''])[0],
    };
  });
  check('V1 侧栏底部常驻显示后台版本（不再只藏在弹窗里）', /vadmin-\\d{3}/.test(v0.rail), v0.rail);
  check('V2 弹窗头版本戳与侧栏同源一致', v0.dialog === (v0.rail.match(/vadmin-\\d{3}/) || [''])[0],
    '弹窗=' + v0.dialog + ' 侧栏=' + v0.rail);
  check('V3 站点版本串（20xxxxxx）与后台版本（vadmin-）是两个不同前缀',
    /^20\\d{6}/.test(v0.siteVer) && v0.dialog.indexOf('vadmin-') === 0,
    '站点=' + v0.siteVer + ' 后台=' + v0.dialog);

  /* ── S · 保存到草稿 ── */""",
    'V 段')

# ── ③ 新增 B · 正文块平铺（本次核心改动）──
rep("""  await page.screenshot({ path: '/tmp/va-new-note.png' });""",
    """  /* ── B · 正文块平铺：不再套娃（vadmin-023）─────────────────
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
      heads: nb.map(x => x.querySelector('.nb-h').innerText.replace(/\\s+/g, ' ').trim()),
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
  check('B8 单元格是可换行的 textarea（长句不被截断）', bAdd.cellsAreTextarea === 4, '个数 ' + bAdd.cellsAreTextarea);

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

  await page.screenshot({ path: '/tmp/va-new-note.png' });""",
    'B 段')

io.open(F, 'w', encoding='utf-8').write(s)
print('✓ verify-notes.js 已补 V/B 两段并动态化版本断言')

# ── ④ verify-picker 的版本断言也去掉写死版本号 ───────────
F2 = 'tools/verify-picker.js'
p = io.open(F2, encoding='utf-8').read()
old = """check('N1 编辑弹窗头带版本戳 vadmin-022（一眼分清旧缓存 / 新 bug）', n0.ver.indexOf('vadmin-022') >= 0, n0.ver.slice(0, 60));"""
new = """check('N1 编辑弹窗头带版本戳（vadmin-NNN，一眼分清旧缓存 / 新 bug）', /vadmin-\\d{3}/.test(n0.ver), n0.ver.slice(0, 60));"""
assert p.count(old) == 1, 'verify-picker N1 锚点 %d 次' % p.count(old)
io.open(F2, 'w', encoding='utf-8').write(p.replace(old, new, 1))
print('✓ verify-picker.js N1 不再写死版本号')
