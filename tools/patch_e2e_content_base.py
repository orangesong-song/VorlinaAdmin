#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E 夹具修复：CONTENT_BASE 生产默认是 https://notify.vorlina.net，
   本地跑测试时不指定就会打到线上 Worker → 401 → 内容 0/15（所有断言假绿/假红）。
   ⇒ 测试必须在页面加载前把 va_content_base 指回本地桩。
   同理修 T6 的越界读取（读不到内容时 tr.children[3] 是 undefined）。"""
import io, os

def patch(rel, pairs):
    F = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', rel))
    s = io.open(F, encoding='utf-8').read()
    n = 0
    for old, new, times in pairs:
        c = s.count(old)
        assert c == times, '%s 锚点命中 %d，预期 %d' % (rel, c, times)
        s = s.replace(old, new, times)
        n += 1
    io.open(F, 'w', encoding='utf-8').write(s)
    print('  ok %-34s %d 处' % (rel, n))


CB = """  /* ⚠️ CONTENT_BASE 默认是生产 Worker —— 本地测试不指回桩就会 401（内容 0/15） */
  await page.evaluateOnNewDocument(o => { try { localStorage.setItem('va_content_base', o) } catch(e){} }, ORIGIN);
"""

patch('tools/verify-product-editor.js', [
    ("""  await page.goto(URL_PAGE, { waitUntil: 'domcontentloaded' });""",
     CB + """  await page.goto(URL_PAGE, { waitUntil: 'domcontentloaded' });""", 1),
])

patch('tools/verify-content.js', [
    ("""  await page.goto(URL_PAGE, { waitUntil: 'domcontentloaded' });""",
     CB + """  await page.goto(URL_PAGE, { waitUntil: 'domcontentloaded' });""", 1),
    ("""    return t ? [...t.querySelectorAll('tbody tr')].reduce((s, tr) => s + Number(tr.children[3].textContent || 0), 0) : -1;""",
     """    return t ? [...t.querySelectorAll('tbody tr')].reduce((s, tr) => s + Number((tr.children[3] || {}).textContent || 0), 0) : -1;""", 1),
])
print('完成')
