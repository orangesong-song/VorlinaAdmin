#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vadmin-011 · 产品编辑器套件判据同步：分类区也卡片化后，产品页不再有表格。
顺手删掉重复的一行 evaluateOnNewDocument（同一行被写了两遍）。"""
import io, os
F = os.path.abspath(os.path.join(os.path.dirname(__file__), 'verify-product-editor.js'))
s = io.open(F, encoding='utf-8').read()

def rep(old, new, tag, n=1):
    global s
    assert s.count(old) == n, '[%s] 出现 %d 次（期望 %d）' % (tag, s.count(old), n)
    s = s.replace(old, new, n)
    print('  ok  %s' % tag)

rep("""  /* ⚠️ CONTENT_BASE 默认是生产 Worker —— 本地测试不指回桩就会 401（内容 0/15） */
  await page.evaluateOnNewDocument(o => { try { localStorage.setItem('va_content_base', o) } catch(e){} }, ORIGIN);
  /* ⚠️ CONTENT_BASE 默认是生产 Worker —— 本地测试不指回桩就会 401（内容 0/15） */
  await page.evaluateOnNewDocument(o => { try { localStorage.setItem('va_content_base', o) } catch(e){} }, ORIGIN);""",
"""  /* ⚠️ CONTENT_BASE 默认是生产 Worker —— 本地测试不指回桩就会 401（内容 0/15） */
  await page.evaluateOnNewDocument(o => { try { localStorage.setItem('va_content_base', o) } catch(e){} }, ORIGIN);""",
    '去掉重复夹具行')

rep("  check('T5 型号区已无表格（只剩分类那张）', list.tables === 1, '实际 ' + list.tables);",
    "  check('T5 产品页已无表格（vadmin-011 分类区也改卡片）', list.tables === 0, '实际 ' + list.tables);",
    'T5 判据同步')

io.open(F, 'w', encoding='utf-8').write(s)
print('verify-product-editor.js 判据已同步')
