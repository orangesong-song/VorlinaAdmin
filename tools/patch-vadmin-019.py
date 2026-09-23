#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vorlina-admin · vadmin-019「上传被 CORS 预检拦死 + 分区直传入口」
2026-09-23 · 用户实锤：vadmin-018 后「仍然没有」上传新图。

真根因（线上探针实锤）：Worker corsFor 的方法白名单
  kind='enquiry'（/media/*、/changes 都落这里）→ 'GET,OPTIONS'
  —— 浏览器预检直接拦死 POST /media/upload、DELETE /media/file/*、POST /changes。
  即：线上从未真正传成功过一张图、媒体库「移除」和「变更对比」也一直是坏的。
  本地 E2E 走 stub 同源，从不触发预检，所以 97 断言全绿也测不出来。
修法：
  ① worker.merged.js corsFor 方法统一 'GET,POST,PUT,DELETE,OPTIONS'
    （所有写路由都要求 Supabase JWT，方法放宽不弱化鉴权；需重贴 CF dashboard）。
  ② index.html：⑤ 图片分区加直传入口（data-pick="null" → 点图追加进画廊、
    画廊为空时顺带设为主图）；主图行也加「选图」。
  ③ 编辑弹窗头加版本戳 vadmin-019 —— 以后「改了没生效」看截图就能分清旧缓存/新 bug。
每处改动带出现次数断言，断言不过整体不落盘。
"""
import io

def rep(s, old, new, n=1, tag=''):
    c = s.count(old)
    assert c == n, '断言失败[%s]：期望 %d 处、实际 %d 处 ->\n%r' % (tag, n, c, old[:120])
    return s.replace(old, new)

# ── ① Worker：corsFor 方法白名单 ─────────────────────────────
F = 'deploy/worker.merged.js'
s = io.open(F, encoding='utf-8').read()
s = rep(s, """function corsFor(request, env, kind) {
  const origin = request.headers.get('Origin') || '';
  const methods = kind === 'content' ? 'GET,PUT,OPTIONS'
    : kind === 'publish' ? 'POST,OPTIONS'
    : 'GET,OPTIONS';""",
"""function corsFor(request, env, kind) {
  const origin = request.headers.get('Origin') || '';
  /* vadmin-019：方法白名单统一放开 —— 之前 /media/*、/changes 落进默认 'GET,OPTIONS'，
     浏览器预检拦死 POST 上传 / DELETE 移除 / POST 变更对比（线上从未传成功过一张图）。
     所有写路由都要求 Supabase JWT，方法放宽不弱化鉴权；预检头按请求回显，不变。 */
  const methods = 'GET,POST,PUT,DELETE,OPTIONS';""", tag='worker.corsFor')
io.open(F, 'w', encoding='utf-8').write(s)
print('OK · worker.merged.js corsFor 已放开（需重贴 CF dashboard）')

# ── ②③ 前端：直传入口 + null 追加分支 + 版本戳 ──────────────
F = 'index.html'
s = io.open(F, encoding='utf-8').read()

# ②-1 产品编辑器 ⑤ 图片：主图行加选图、分区加上传入口
s = rep(s, """  const imgBody = '<label class="ed-field"><span class="ed-k">主图 · 从本型号图库里选</span>'
    + '<select class="ed-in" data-ed="' + escAttr(JSON.stringify(base.concat(['images','hero']))) + '">'
    + (heroOpts || '<option value="">（画廊为空）</option>') + '</select></label>'
    + '<div class="edsec-note">缩略图取自 imagery 图库；点「设为主图」立即切换（仍需保存草稿）。</div>'
    + edHeroStrip(imgs)
    + edNodeHTML(base.concat(['images','usable']), usable, '画廊图片（文件名列表）',
                 (S.sub && S.sub.images) ? S.sub.images : null, 'usable');""",
"""  const imgBody = '<label class="ed-field"><span class="ed-k">主图 · 从本型号图库里选</span>'
    + '<span class="ed-pickrow"><select class="ed-in" data-ed="' + escAttr(JSON.stringify(base.concat(['images','hero']))) + '">'
    + (heroOpts || '<option value="">（画廊为空）</option>') + '</select>'
    + '<button type="button" class="btn ghost sm" data-pick="' + escAttr(JSON.stringify(base.concat(['images','hero']))) + '">选图</button></span></label>'
    + '<div class="edsec-note">缩略图取自 imagery 图库；点「设为主图」立即切换（仍需保存草稿）。</div>'
    + edHeroStrip(imgs)
    + '<div class="edsec-note">图库里没有想要的图？点下面按钮，弹层里「上传新图」，传完点它就追加进画廊（保存草稿后发布生效）。</div>'
    + '<div style="margin:10px 0"><button type="button" class="btn ghost sm" data-pick="null">＋ 上传新图 / 从图库追加</button></div>'
    + edNodeHTML(base.concat(['images','usable']), usable, '画廊图片（文件名列表）',
                 (S.sub && S.sub.images) ? S.sub.images : null, 'usable');""", tag='fe.imgBody')

# ②-2 点选处理器：PICK.path === null 时点图 = 追加进本型号画廊
s = rep(s, """  const pickItem = e.target.closest('[data-pickitem]');
  if (pickItem && PICK.path){
    edSet(ED.doc, PICK.path, pickItem.dataset.pickitem);
    closePick(); edRender(); return;
  }""",
"""  const pickItem = e.target.closest('[data-pickitem]');
  if (pickItem && PICK.path){
    edSet(ED.doc, PICK.path, pickItem.dataset.pickitem);
    closePick(); edRender(); return;
  }
  if (pickItem && PICK.path === null && ED && ED.path === 'data/products.json'){
    /* vadmin-019：无目标格的上传/选图 —— 点图直接追加进本型号画廊；画廊原本为空就顺带设为主图 */
    const p0 = edGet(ED.doc, ED.sub) || {};
    if (!p0.images) p0.images = { hero: '', usable: [] };
    if (!Array.isArray(p0.images.usable)) p0.images.usable = [];
    if (p0.images.usable.indexOf(pickItem.dataset.pickitem) < 0) p0.images.usable.push(pickItem.dataset.pickitem);
    if (!p0.images.hero) p0.images.hero = pickItem.dataset.pickitem;
    closePick(); edRender(); return;
  }""", tag='fe.pickNull')

# ③ 编辑弹窗头版本戳（以后每次前端补丁必须同步改这里的版本号）
s = rep(s, """    <div class="ed-head">
      <span class="t" id="edTitle">编辑</span>
      <button class="btn ghost sm" id="edClose">关闭</button>""",
"""    <div class="ed-head">
      <span class="t" id="edTitle">编辑</span>
      <!-- vadmin 版本戳：每次前端补丁必须同步改这里（用户截图带它 = 一眼分清旧缓存/新 bug） -->
      <span class="mono" style="font-size:10px;color:var(--muted)">vadmin-019</span>
      <button class="btn ghost sm" id="edClose">关闭</button>""", tag='fe.verStamp')

io.open(F, 'w', encoding='utf-8').write(s)
print('OK · index.html 三处补丁落盘（直传入口 / null 追加 / 版本戳）')

# ── 验收脚本：插入 N 段 ─────────────────────────────────────
F = 'tools/verify-picker.js'
s = io.open(F, encoding='utf-8').read()
s = rep(s, """  /* ── H · PUT 请求必须带 Authorization（vadmin-017 头合并修复）── */""",
"""  /* ── N · ⑤ 图片分区的直传入口（vadmin-019）──────────────── */
  section('N · ⑤ 图片分区的直传入口（vadmin-019）');
  const n0 = await page.evaluate(() => ({
    ver: (document.querySelector('#edWrap .ed-head') || {}).textContent || '',
    heroPick: [...document.querySelectorAll('#edBody [data-pick]')]
      .some(b => /"images","hero"/.test(b.dataset.pick || '')),
    addBtn: !!document.querySelector('#edBody [data-pick="null"]'),
    usableN: (function () { try { return edGet(ED.doc, ED.sub.concat(['images','usable'])).length } catch (e) { return -1 } })(),
  }));
  check('N1 编辑弹窗头带版本戳 vadmin-019（一眼分清旧缓存 / 新 bug）', n0.ver.indexOf('vadmin-019') >= 0, n0.ver.slice(0, 60));
  check('N2 主图行有「选图」按钮', n0.heroPick);
  check('N3 分区有「上传新图 / 从图库追加」入口', n0.addBtn);
  await page.evaluate(() => document.querySelector('#edBody [data-pick="null"]').click());
  await page.waitForFunction(() => !document.getElementById('pickPanel').hidden, { timeout: 8000 });
  await page.waitForFunction(() => document.querySelectorAll('#pickBody .pick-item').length > 0, { timeout: 15000 });
  const addName = await page.evaluate(() => {
    let u = [];
    try { u = edGet(ED.doc, ED.sub.concat(['images','usable'])) || [] } catch (e) {}
    const it = [...document.querySelectorAll('#pickBody .pick-item')]
      .find(x => u.indexOf(x.dataset.pickitem) < 0);          /* 挑一个不在画廊里的，保证是真追加 */
    if (!it) return null;
    it.click();
    return it.dataset.pickitem;
  });
  await new Promise(r => setTimeout(r, 300));
  const n1 = await page.evaluate(name => {
    const u = edGet(ED.doc, ED.sub.concat(['images','usable'])) || [];
    return { closed: document.getElementById('pickPanel').hidden, n: u.length, has: u.indexOf(name) >= 0 };
  }, addName);
  check('N4 点图后弹层关闭且真追加进画廊（' + n0.usableN + ' → ' + n1.n + '，' + addName + '）',
    !!addName && n1.closed && n1.n === n0.usableN + 1 && n1.has, 'usable=' + n1.n + ' closed=' + n1.closed);

  /* ── H · PUT 请求必须带 Authorization（vadmin-017 头合并修复）── */""", tag='verify.N')
io.open(F, 'w', encoding='utf-8').write(s)
print('OK · verify-picker.js 已插入 N 段')
