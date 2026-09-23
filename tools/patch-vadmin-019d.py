#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vorlina-admin · vadmin-019d「桩站路径解码 + 缩略图断言升级 + 用例自备夹具」
2026-09-23

① serve-local.py 的 /media/file 读、删都没做 URL 解码 → 中文名上传图在桩站上
   一直读不到（默默回源 404 = 裂图）、也删不掉（404 not_found）。
   线上 Worker 是对的（有 decodeURIComponent），**只有本地替身漏了** ——
   而「断言只查 img.src 有没有」永远看不出裂图。桩与真身行为不一致 = 守卫在骗人。
② verify-picker：U5 从「数一数有几张已上传图」升级为「点开夹具图的缩略图，
   必须真的解码出来（naturalWidth>0）」；夹具由用例自己创建、结束自己清理
   —— 不再依赖图库里恰好有别人遗留的文件（上一轮就是这样假通过的）。
"""
import io

def rep(s, old, new, n=1, tag=''):
    c = s.count(old)
    assert c == n, '断言失败[%s]：期望 %d、实际 %d ->\n%r' % (tag, n, c, old[:120])
    return s.replace(old, new)

# ── ① 桩站：路径解码 ────────────────────────────────────────
F = 'tools/serve-local.py'
s = io.open(F, encoding='utf-8').read()
s = rep(s, "from urllib.parse import urlparse, parse_qs",
           "from urllib.parse import urlparse, parse_qs, unquote", tag='stub.import')
s = rep(s, """        name = os.path.basename(u.path[len('/media/file/'):])
        p = os.path.join(MEDIA_DIR, name)
        if os.path.isfile(p):
            # ⚠️ 不用 os.remove：本机（NAS 卷 + 系统安全机制）会拦住删除并抛错。""",
"""        # ⚠️ 必须 URL 解码：前端发的是 encodeURIComponent(name)，中文名不解码就找不到文件
        #    （线上 Worker 用 decodeURIComponent，桩与真身行为必须一致 —— 否则守卫在骗人）
        name = os.path.basename(unquote(u.path[len('/media/file/'):]))
        p = os.path.join(MEDIA_DIR, name)
        if os.path.isfile(p):
            # ⚠️ 不用 os.remove：本机（NAS 卷 + 系统安全机制）会拦住删除并抛错。""", tag='stub.delete.decode')
s = rep(s, """    def do_GET_media_file(self, rel):
        name = os.path.basename(rel)""",
"""    def do_GET_media_file(self, rel):
        name = os.path.basename(unquote(rel))      # 同上：与 Worker 的 decodeURIComponent 对齐""", tag='stub.get.decode')
io.open(F, 'w', encoding='utf-8').write(s)
print('OK · serve-local.py 读/删路径已解码')

# ── ② 验收脚本：自备夹具 + 缩略图真解码断言 ────────────────
F = 'tools/verify-picker.js'
s = io.open(F, encoding='utf-8').read()

s = rep(s, """const SHOT = path.join(__dirname, '..', '_not-for-site', '验收截图-20260923', '30-选图弹层.png');""",
"""const SHOT = path.join(__dirname, '..', '_not-for-site', '验收截图-20260923', '30-选图弹层.png');

/* 自备夹具：往本地「R2 桶」放一张真·1×1 PNG（不是 8 字节垃圾字节 —— 垃圾图
   永远解不出来，断言就变成废的）。用例自己创建、自己清理，不靠别人遗留。 */
const MEDIA_DIR = path.join(__dirname, '..', '.local-drafts', 'media');
const FIXTURE = 'e2e-常驻探针-1x1.png';
const PNG_1X1 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=';
fs.mkdirSync(MEDIA_DIR, { recursive: true });
fs.writeFileSync(path.join(MEDIA_DIR, FIXTURE), Buffer.from(PNG_1X1, 'base64'));""", tag='verify.fixture')

s = rep(s, """  const u0 = await page.evaluate(e0 => {
    const items = [...document.querySelectorAll('#pickBody .pick-item')];
    return {
      n: items.length,
      withImg: items.filter(x => (x.querySelector('img') || {}).src).length,
      uploaded: items.filter(x => /\\/media\\/file\\/img\\//.test((x.querySelector('img') || {}).src || '')).length,
      hasUpload: !!document.getElementById('pickFile'),
      targetExists: items.some(x => x.dataset.pickitem === e0),
    };
  }, EXPECT.usable0);""",
"""  const u0 = await page.evaluate(e0 => {
    const items = [...document.querySelectorAll('#pickBody .pick-item')];
    return {
      n: items.length,
      withImg: items.filter(x => (x.querySelector('img') || {}).src).length,
      uploaded: items.filter(x => /\\/media\\/file\\/img\\//.test((x.querySelector('img') || {}).src || '')).length,
      hasUpload: !!document.getElementById('pickFile'),
      targetExists: items.some(x => x.dataset.pickitem === e0),
    };
  }, EXPECT.usable0);
  /* 夹具图的缩略图必须真的解码出来 —— 只查 src 会漏掉「路径没解码 / 回源 404」这类裂图 */
  const fixThumb = await page.evaluate(async name => {
    const el = [...document.querySelectorAll('#pickBody .pick-item')].find(x => x.dataset.pickitem === name);
    if (!el) return { found: false };
    const img = el.querySelector('img');
    const t0 = Date.now();
    while (!(img.complete && img.naturalWidth > 0) && Date.now() - t0 < 6000) await new Promise(r => setTimeout(r, 100));
    return { found: true, w: img.naturalWidth, src: img.src };
  }, FIXTURE);""", tag='verify.u5probe')

s = rep(s, """  check('U5 已上传的图走 Worker 直读（线上还没有，必须如此才不裂图）', u0.uploaded > 0, '上传区 ' + u0.uploaded + ' 张');""",
"""  check('U5 已上传的图走 Worker 直读（src 前缀 /media/file/img/）',
    u0.uploaded > 0 && /\\/media\\/file\\/img\\//.test(fixThumb.src || ''), '上传区 ' + u0.uploaded + ' 张 · src=' + (fixThumb.src || ''));
  check('U6 已上传图的缩略图真能显示（naturalWidth>0 —— 只查 src 会漏 URL 编码/回源 404 类裂图）',
    fixThumb.found && fixThumb.w > 0, JSON.stringify(fixThumb));""", tag='verify.u5assert')

s = rep(s, """  check('Z1 全程无 JS 异常', jsErrors.length === 0, jsErrors.slice(0, 3).join(' | '));

  await browser.close();""",
"""  check('Z1 全程无 JS 异常', jsErrors.length === 0, jsErrors.slice(0, 3).join(' | '));

  /* 夹具清场（本地桶，直接删文件；媒体路由的删已由 PL4 覆盖） */
  try { fs.unlinkSync(path.join(MEDIA_DIR, FIXTURE)) } catch (e) {}

  await browser.close();""", tag='verify.fixtureClean')
io.open(F, 'w', encoding='utf-8').write(s)
print('OK · verify-picker.js 已加夹具与缩略图真解码断言')
