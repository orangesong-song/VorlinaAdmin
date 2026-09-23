#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vadmin-011 · 守卫判据随 UI 同步：分类表 → 分类卡片。
改了 UI 不改断言 = 守卫装瞎（D123）。"""
import io, os
F = os.path.abspath(os.path.join(os.path.dirname(__file__), 'verify-content.js'))
s = io.open(F, encoding='utf-8').read()

def rep(old, new, tag):
    global s
    assert s.count(old) == 1, '[%s] 出现 %d 次' % (tag, s.count(old))
    s = s.replace(old, new, 1)
    print('  ok  %s' % tag)

rep("      cards: document.querySelectorAll('#view .pcard').length,",
    "      cards: document.querySelectorAll('#view .pcard').length,\n      ccards: document.querySelectorAll('#view .ccard').length,",
    'go() 增加分类卡片计数')

rep("""  /* vadmin-010：型号区已由表格改为卡片流（缩略图 + 状态点），本页只剩分类那一张表。 */
  check('T3 型号卡片 16 张（本页剩 1 张表：分类）',
    pr.cards === EXPECT.products && pr.tableCount === 1,
    '卡片 ' + pr.cards + ' 张 · 表 ' + pr.tableCount + ' 张');
  check('T3b 卡片带缩略图元素（图库按 sku 匹配）',
    await page.evaluate(() => document.querySelectorAll('#view .pcard-thumb img').length) === EXPECT.products);""",
"""  /* vadmin-010：型号区改卡片流；vadmin-011：分类区也改卡片流 —— 本页不再有表格。 */
  check('T3 型号卡片 16 张 + 分类卡片 6 张（本页已无表格）',
    pr.cards === EXPECT.products && pr.ccards === EXPECT.categories && pr.tableCount === 0,
    '型号卡 ' + pr.cards + ' · 分类卡 ' + pr.ccards + ' · 表 ' + pr.tableCount);
  check('T3b 卡片带缩略图元素（图库按 sku 匹配）',
    await page.evaluate(() => document.querySelectorAll('#view .pcard-thumb img').length) === EXPECT.products);
  check('T3c 分类卡带卡片图预览（assets/img 同名文件）',
    await page.evaluate(() => document.querySelectorAll('#view .ccard-thumb img').length) === EXPECT.categories);""",
    'T3 判据同步')

rep("""  const catSum = await page.evaluate(() => {
    const t = [...document.querySelectorAll('#view table.tbl')][0];   // vadmin-010：0 = 分类表
    return t ? [...t.querySelectorAll('tbody tr')].reduce((s, tr) => s + Number((tr.children[3] || {}).textContent || 0), 0) : -1;
  });
  check('T6 分类表在架款数合计 = 16（派生值正确）', catSum === EXPECT.products, '实际 ' + catSum);""",
"""  /* vadmin-011：分类区改卡片后，「在架 N 款」写在 .ccard-meta 里 */
  const catSum = await page.evaluate(() =>
    [...document.querySelectorAll('#view .ccard .ccard-meta')]
      .reduce((s, el) => s + Number((/在架\\s*(\\d+)\\s*款/.exec(el.textContent) || [0, 0])[1]), 0));
  check('T6 分类卡在架款数合计 = 16（派生值正确）', catSum === EXPECT.products, '实际 ' + catSum);""",
    'T6 判据同步')

io.open(F, 'w', encoding='utf-8').write(s)
print('verify-content.js 判据已同步')
