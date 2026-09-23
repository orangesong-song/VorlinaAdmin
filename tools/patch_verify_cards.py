#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归套件跟着 UI 走（vadmin-010）：产品列表由表格改卡片流后，
   verify-content.js 的 T3/T6 判据必须同步改，否则「守卫报绿但页面已变」。
   教训：守卫的判据会骗人 —— 改 UI 就要改断言，且断言要盯真实字面量。"""
import io, os

F = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools', 'verify-content.js'))
src = io.open(F, encoding='utf-8').read()
n = 0


def rep(old, new, times=1):
    global src, n
    c = src.count(old)
    assert c == times, '锚点命中 %d 次，预期 %d 次：%s' % (c, times, old[:60])
    src = src.replace(old, new, times)
    n += 1


# 1) go() 返回值补 cards 计数
rep("""      rows: document.querySelectorAll('#view table.tbl tbody tr').length,""",
    """      rows: document.querySelectorAll('#view table.tbl tbody tr').length,
      cards: document.querySelectorAll('#view .pcard').length,""")

# 2) T3：型号由表格改卡片
rep("""  check('T3 型号表 16 行（本页两张表，只数第一张）',
    pr.firstRows === EXPECT.products && pr.tableCount === 2,
    '首表 ' + pr.firstRows + ' 行 · 共 ' + pr.tableCount + ' 张表');""",
    """  /* vadmin-010：型号区已由表格改为卡片流（缩略图 + 状态点），本页只剩分类那一张表。 */
  check('T3 型号卡片 16 张（本页剩 1 张表：分类）',
    pr.cards === EXPECT.products && pr.tableCount === 1,
    '卡片 ' + pr.cards + ' 张 · 表 ' + pr.tableCount + ' 张');
  check('T3b 卡片带缩略图元素（图库按 sku 匹配）',
    await page.evaluate(() => document.querySelectorAll('#view .pcard-thumb img').length) === EXPECT.products);""")

# 3) T6：分类表索引由 1 → 0（产品表没了）
rep("""    const t = [...document.querySelectorAll('#view table.tbl')][1];""",
    """    const t = [...document.querySelectorAll('#view table.tbl')][0];   // vadmin-010：0 = 分类表""")

io.open(F, 'w', encoding='utf-8').write(src)
print('完成：%d 处替换 → %s' % (n, F))
