#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vorlina-admin · vadmin-019e「修 T9 时序竞态（不是产品缺陷，是断言不等）」
2026-09-23 · 全量回归时 verify-login 红 1 条：T9「boss 看到回滚可用」读到的是
「正在从仓库读取内容…」—— 固定 sleep 250ms 在内容 15 份 JSON 读完前就取值了。
修法：改成等条件（等到页面出现「回滚可用/不可用」再断言），超时后仍按真值判红
（不吞掉真失败）。
"""
import io

F = 'tools/verify-login.js'
s = io.open(F, encoding='utf-8').read()

def rep(old, new, n=1):
    global s
    c = s.count(old)
    assert c == n, '断言失败：期望 %d、实际 %d ->\n%r' % (n, c, old[:140])
    s = s.replace(old, new)

WAIT = """  /* 等「回滚可用/不可用」真的渲染出来再断言 —— 固定 sleep 会读到「正在从仓库读取内容…」
     （2026-09-23 全量回归实测翻车；等不到就超时判红，不掩盖真失败） */
  await page.waitForFunction(
    () => /回滚(可用|不可用)/.test(document.getElementById('view').textContent),
    { timeout: 15000 }).catch(() => {});
"""

rep("""  await page.evaluate(() => { location.hash = '#/releases'; });
  await new Promise(r => setTimeout(r, 250));
  s = await state();
  check('T9 业务员看到「回滚不可用」', /回滚不可用/.test(s.view), s.view.slice(0, 120));""",
"""  await page.evaluate(() => { location.hash = '#/releases'; });
""" + WAIT + """  s = await state();
  check('T9 业务员看到「回滚不可用」', /回滚不可用/.test(s.view), s.view.slice(0, 120));""")

rep("""  await page.evaluate(() => { location.hash = '#/releases'; });
  await new Promise(r => setTimeout(r, 250));
  s = await state();
  check('T9 boss 看到「回滚可用」', /回滚可用/.test(s.view), s.view.slice(0, 120));""",
"""  await page.evaluate(() => { location.hash = '#/releases'; });
""" + WAIT + """  s = await state();
  check('T9 boss 看到「回滚可用」', /回滚可用/.test(s.view), s.view.slice(0, 120));""")

io.open(F, 'w', encoding='utf-8').write(s)
print('OK · verify-login.js T9 两处竞态已改为等条件')
