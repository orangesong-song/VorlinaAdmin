#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vorlina-admin · vadmin-018「弹层内上传要有反馈」
2026-09-23 · 用户实锤：选图弹层里点「上传新图」，界面毫无反应（像「没有上传新图」）。

根因：mediaUploadFiles 的结果只写 MEDIA.msg，展示它的 rerenderMedia()
在产品编辑页直接 return（current !== 'media'）；弹层里也没有任何消息区
—— 成功也好失败也好，运营看到的都是「没动静」。

修法（弹层自闭环反馈，复用 admin.css 现成的 .notice / .safe / .gold）：
  ① pickFile.onchange 改为非阻塞：点了立刻渲染 busy 提示，完成后重渲列表；
  ② renderPickGrid 顶部加 上传中 / 上传结果 / 图库错误 三种横幅；
  ③ openPick 清掉上一次残留的 MEDIA.msg，别让它串场。
每处改动带出现次数断言 —— 断言不过就整体不落盘（守卫纪律）。
"""
import io, sys

F = 'index.html'
s = io.open(F, encoding='utf-8').read()
orig = s

def rep(old, new, n=1):
    global s
    c = s.count(old)
    assert c == n, '断言失败：期望 %d 处、实际 %d 处 ->\n%r' % (n, c, old[:120])
    s = s.replace(old, new)

# ── ① openPick 清残留消息 ─────────────────────────────────────
rep("""function openPick(pathStr){
  if (!ED) return;
  PICK.path = JSON.parse(pathStr);
  ensurePickDom();""",
"""function openPick(pathStr){
  if (!ED) return;
  PICK.path = JSON.parse(pathStr);
  MEDIA.msg = ''; MEDIA.msgKind = '';   /* vadmin-018 清掉上一次的上传结果，别串场 */
  ensurePickDom();""")

# ── ② onchange：点了立刻给 busy 反馈，完成后重渲 ──────────────
rep("""  document.getElementById('pickFile').onchange = async e => {
    const fs = Array.from(e.target.files || []);
    e.target.value = '';
    if (!fs.length) return;
    await mediaUploadFiles(fs);        /* 复用上传管线：R2 + cms 分支双写 */
    renderPickGrid();
  };""",
"""  document.getElementById('pickFile').onchange = e => {
    const fs = Array.from(e.target.files || []);
    e.target.value = '';
    if (!fs.length) return;
    const p = mediaUploadFiles(fs);    /* 复用上传管线：R2 + cms 分支双写 */
    renderPickGrid();                  /* vadmin-018 busy 提示立刻可见（修复：上传无反馈 = 像「没上传」） */
    p.then(renderPickGrid).catch(renderPickGrid);
  };""")

# ── ③ renderPickGrid：上传中 / 结果 / 图库错误 三种横幅 ───────
rep("""  const items = pickItems();
  const note = MEDIA.error ? '<p class="dim">' + esc(MEDIA.error) + '</p>' : '';
  body.innerHTML = note + (items.length""",
"""  const items = pickItems();
  /* vadmin-018 弹层内反馈：上传中 → 结果横幅（成功 safe / 失败 gold），复用 admin.css 的 .notice */
  const busy = MEDIA.busy ? '<div class="notice">正在上传，传完会自动出现在下面…</div>' : '';
  const upmsg = (!MEDIA.busy && MEDIA.msg) ? '<div class="notice ' + (MEDIA.msgKind || '') + '">' + esc(MEDIA.msg) + '</div>' : '';
  const note = MEDIA.error ? '<p class="dim">' + esc(MEDIA.error) + '</p>' : '';
  body.innerHTML = busy + upmsg + note + (items.length""")

assert s != orig
io.open(F, 'w', encoding='utf-8').write(s)
print('OK · vadmin-018 三处补丁全部命中并落盘')
