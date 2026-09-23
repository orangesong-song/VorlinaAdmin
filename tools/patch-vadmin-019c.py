#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vorlina-admin · vadmin-019c「上传用例自隔离」
2026-09-23 · 上一次跑 PL 段挂了 PL3，根因不是产品缺陷而是用例不自隔离：
  临时文件名固定 → 前一次残留让「等它出现」的断言假通过 → 读横幅时上传还在途中。
  且清场失败被 .catch(()=>{}) 吞掉，垃圾文件静默累积（图库 57 → 58）。
修法：① 文件名带时间戳，每次唯一；② PL0 前置断言「此前不存在」；
     ③ PL2 把 waitForFunction 结果变成真断言；④ PL4 断言清场成功（DELETE 响应 + 列表已无）。
"""
import io

F = 'tools/verify-picker.js'
s = io.open(F, encoding='utf-8').read()

OLD = """  const UP_NAME = 'e2e-上传反馈测试.png';
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
  await page.waitForFunction(name => [...document.querySelectorAll('#pickBody .pick-item')]
    .some(x => x.dataset.pickitem === name), { timeout: 10000 }, UP_NAME);
  const doneTxt = await page.evaluate(() => {
    const n = document.querySelector('#pickBody .notice.safe');
    return n ? n.textContent : '';
  });
  check('PL2 上传完成后新图出现在弹层列表（点一下就能填）', true);
  check('PL3 显示结果横幅（已上传 ' + UP_NAME + '）', /已上传 1 个/.test(doneTxt) && doneTxt.indexOf(UP_NAME) >= 0, '实际：' + doneTxt);
  /* 清场：删测试文件 + 恢复 fetch + 刷新列表，不给后续断言留脏数据 */
  await page.evaluate(async name => {
    await fetch(CONTENT_BASE + '/media/file/img/' + encodeURIComponent(name),
      { method: 'DELETE', headers: { Authorization: 'Bearer ' + sbToken() } });
    window.fetch = window._origFetch;
    await mediaLoad();
    renderPickGrid();
  }, UP_NAME).catch(() => {});
  await new Promise(r => setTimeout(r, 400));
"""

NEW = """  /* 文件名带时间戳：每次唯一 —— 否则前一次残留会让「等它出现」假通过（2026-09-23 实测翻车） */
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
"""

assert s.count(OLD) == 1, 'PL 段匹配失败：命中 %d 次' % s.count(OLD)
s = s.replace(OLD, NEW)
io.open(F, 'w', encoding='utf-8').write(s)
print('OK · verify-picker.js PL 段已自隔离（PL0/PL2/PL4 三处补强）')
