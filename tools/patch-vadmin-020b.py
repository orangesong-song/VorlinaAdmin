# -*- coding: utf-8 -*-
"""
vadmin-020b · 给 verify-picker.js 增补 IMG 段（上传后真的进型号图库）

覆盖 vadmin-020 的四条新行为：
  IMG1 上传的文件名被登记进 build/data/imagery.json[sku].items（src + url=/assets/img/<name>）
  IMG2 「主图」下拉里出现该图（此前下拉只列已有画廊 —— 用户永远找不到新图）
  IMG3 编辑页缩略图条里该图有真 URL（回退 R2 直读，不再「图库未匹配」）
  IMG4 保存草稿会一并 PUT imagery.json（否则下拉有名字、官网取不到 url）
"""
import io

F = 'tools/verify-picker.js'
s = io.open(F, encoding='utf-8').read()
orig = s
n = 0

def rep(old, new, label):
    global s, n
    c = s.count(old)
    assert c == 1, '[%s] 锚点命中 %d 次: %r' % (label, c, old[:90])
    s = s.replace(old, new)
    n += 1
    print('  ✓ %s' % label)

# 头部注释补版本说明
rep(""" * 断言原则：真源字面量、交互真生效、请求头真的带上了。
 */""",
""" * vadmin-020 增补：上传的图必须**登记进本型号图库(imagery.json)** ——
 *   媒体库(R2) 与 型号图库 是两套列表，主图下拉/缩略图/官网取图 URL 全部只认 imagery。
 *   不登记 ⇒ 图传上去了，后台哪儿都看不到（下拉列不出、缩略图「图库未匹配」、官网无 url）。
 *
 * 断言原则：真源字面量、交互真生效、请求头真的带上了。
 */""",
'头部注释补 vadmin-020')

# 在清场之前插入 IMG 段
rep("""  /* 清场必须断言 —— 之前被 .catch 吞掉，垃圾文件静默累积（图库 57→58） */""",
"""  /* ── IMG · 上传的图必须进「本型号图库」（vadmin-020）──────────────
     断的是「图传上去了但哪儿都看不到」这条断链：媒体库 ≠ 型号图库。
     此刻 UP_NAME 刚上传成功、还在图库里，正好用来断言。 */
  section('IMG · 上传后登记进型号图库（vadmin-020）');
  const img1 = await page.evaluate(name => {
    const sku = (function () { try { return edGet(ED.doc, ED.sub).sku } catch (e) { return null } })();
    const doc = STORE.files['build/data/imagery.json'] || {};
    const items = (doc[sku] && doc[sku].items) || [];
    const hit = items.find(it => it && it.src === name) || null;
    return { sku: sku, hit: hit, total: items.length };
  }, UP_NAME);
  check('IMG1 上传的文件名登记进 imagery 图库[' + img1.sku + '] 且带 /assets/img/ url',
    !!img1.hit && img1.hit.url === '/assets/img/' + UP_NAME,
    JSON.stringify(img1.hit || null));

  const img2 = await page.evaluate(name => {
    edRender();                                   /* 编辑页重绘，看下拉是不是真的多了一项 */
    const sel = [...document.querySelectorAll('#edBody select[data-ed]')]
      .find(x => /"images","hero"/.test(x.dataset.ed));
    if (!sel) return { found: false };
    const opt = [...sel.querySelectorAll('option')].find(o => o.value === name);
    const grp = opt ? (opt.closest('optgroup') || {}).label || '' : '';
    return { found: !!opt, grp: grp, groups: [...sel.querySelectorAll('optgroup')].map(g => g.label) };
  }, UP_NAME);
  check('IMG2 「主图」下拉能直接看到刚上传的图（分组：' + img2.grp + '）',
    img2.found, '分组=' + JSON.stringify(img2.groups));

  const img3 = await page.evaluate(name => {
    const el = [...document.querySelectorAll('#edBody .ed-thumb')]
      .find(x => (x.querySelector('span.mono') || {}).textContent === name);
    if (!el) return { found: false };
    const img = el.querySelector('img');
    return { found: true, src: img ? img.src : '', ph: !!el.querySelector('.ed-thumb-ph') };
  }, UP_NAME);
  check('IMG3 编辑页缩略图用真 URL 显示（回退 R2 直读，不再「图库未匹配」灰框）',
    img3.found && /\\/media\\/file\\/img\\//.test(img3.src) && !img3.ph, JSON.stringify(img3));

  /* IMG4：保存草稿是否一并提交 imagery.json（否则下拉有名字、官网取不到 url） */
  const img4 = await page.evaluate(async () => {
    const seen = [];
    const orig = window.fetch;
    window.fetch = (url, opts) => {
      if (/\\/content$/.test(String(url)) && opts && opts.method === 'PUT') {
        let p = ''; try { p = JSON.parse(opts.body).path } catch (e) {}
        seen.push(p);
      }
      return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    };
    try { await saveEd() } catch (e) {}
    window.fetch = orig;
    return seen;
  });
  check('IMG4 保存草稿会一并提交 imagery.json（新图登记才算落地）',
    img4.indexOf('build/data/imagery.json') >= 0, '实际 PUT：' + JSON.stringify(img4));

  /* 清场必须断言 —— 之前被 .catch 吞掉，垃圾文件静默累积（图库 57→58） */""",
'插入 IMG 段')

assert s != orig
io.open(F, 'w', encoding='utf-8').write(s)
print('\nOK · verify-picker.js 已插入 IMG 段（%d 处）' % n)
