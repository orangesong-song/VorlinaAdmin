# -*- coding: utf-8 -*-
"""vadmin-020d · verify-picker.js：IMG 段整体替换为「真实路径」版（走＋上传新图入口）"""
import io

F = 'tools/verify-picker.js'
s = io.open(F, encoding='utf-8').read()

i = s.find("  /* ── IMG · 上传的图必须进「本型号图库」（vadmin-020）")
j = s.find("  /* 清场必须断言 —— 之前被 .catch 吞掉")
assert i > 0 and j > i, 'IMG 段范围定位失败 i=%d j=%d' % (i, j)
print('  ✓ 定位旧 IMG 段：字符 %d → %d' % (i, j))

new_img = """  /* ── IMG · 走真实路径：「＋ 上传新图 / 从图库追加」入口上传（vadmin-020）──
     上传的图必须 ① 登记进 imagery 图库 ② 自动进本型号画廊 ③ 主图下拉立刻可见 ④ 缩略图真能显示。
     断的是「图传上去了但哪儿都看不到」这条断链：媒体库(R2) ≠ 型号图库(imagery)。 */
  section('IMG · 上传后直接进型号图库与画廊（vadmin-020）');
  await page.evaluate(() => document.querySelector('#edBody [data-pick="null"]').click());
  await page.waitForFunction(() => !document.getElementById('pickPanel').hidden, { timeout: 8000 });
  await page.waitForFunction(() => document.querySelectorAll('#pickBody .pick-item').length > 0, { timeout: 15000 });
  const UP2 = 'e2e-' + Date.now() + '-归组测试.png';
  const pre2 = await page.evaluate(name => [...document.querySelectorAll('#pickBody .pick-item')]
    .some(x => x.dataset.pickitem === name), UP2);
  check('IMG0 前置：本次文件名此前不在列表里（避免假通过）', !pre2);
  const galBefore = await page.evaluate(() => {
    try { return (edGet(ED.doc, ED.sub.concat(['images','usable'])) || []).length } catch (e) { return -1 }
  });
  await page.evaluate(name => {
    const dt = new DataTransfer();
    dt.items.add(new File([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])], name, { type: 'image/png' }));
    const inp = document.getElementById('pickFile');
    inp.files = dt.files;
    inp.dispatchEvent(new Event('change', { bubbles: true }));
  }, UP2);
  await page.waitForFunction(name => (MEDIA.items || []).some(it => it.name === name),
    { timeout: 15000 }, UP2);

  const img1 = await page.evaluate(name => {
    const sku = (function () { try { return edGet(ED.doc, ED.sub).sku } catch (e) { return null } })();
    const doc = STORE.files['build/data/imagery.json'] || {};
    const items = (doc[sku] && doc[sku].items) || [];
    const hit = items.find(it => it && it.src === name) || null;
    const gal = (function () { try { return edGet(ED.doc, ED.sub.concat(['images','usable'])) || [] } catch (e) { return [] } })();
    return { sku: sku, hit: hit, inGallery: gal.indexOf(name) >= 0, galN: gal.length };
  }, UP2);
  check('IMG1 上传即登记进 imagery 图库[' + img1.sku + ']（src + /assets/img/ url 齐全）',
    !!img1.hit && img1.hit.url === '/assets/img/' + UP2, JSON.stringify(img1.hit || null));
  check('IMG2 从「＋上传新图」入口上传 ⇒ 直接进本型号画廊（' + galBefore + ' → ' + img1.galN + '）',
    img1.inGallery);

  const img2 = await page.evaluate(name => {
    const sel = [...document.querySelectorAll('#edBody select[data-ed]')]
      .find(x => /"images","hero"/.test(x.dataset.ed));
    if (!sel) return { found: false };
    const opt = [...sel.querySelectorAll('option')].find(o => o.value === name);
    return { found: !!opt, val: sel.value, groups: [...sel.querySelectorAll('optgroup')].map(g => g.label) };
  }, UP2);
  check('IMG3 「主图」下拉里立刻能看到它（不用去媒体库复制文件名）',
    img2.found, '分组=' + JSON.stringify(img2.groups));

  const img3 = await page.evaluate(async name => {
    const el = [...document.querySelectorAll('#edBody .ed-thumb')]
      .find(x => (x.querySelector('span.mono') || {}).textContent === name);
    if (!el) return { found: false };
    const img = el.querySelector('img');
    if (img) { const t0 = Date.now(); while (!(img.complete && img.naturalWidth > 0) && Date.now() - t0 < 5000) await new Promise(r => setTimeout(r, 100)); }
    return { found: true, src: img ? img.src : '', w: img ? img.naturalWidth : 0, ph: !!el.querySelector('.ed-thumb-ph') };
  }, UP2);
  check('IMG4 编辑页缩略图真能显示（回退 R2 直读 · naturalWidth>0，不再「图库未匹配」灰框）',
    img3.found && img3.w > 0 && !img3.ph, JSON.stringify(img3));

  /* IMG5：保存草稿是否一并提交 imagery.json（否则下拉有名字、官网取不到 url） */
  const img5 = await page.evaluate(async () => {
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
  check('IMG5 保存草稿一并提交 imagery.json（新图登记才算落地）',
    img5.indexOf('build/data/imagery.json') >= 0, '实际 PUT：' + JSON.stringify(img5));

  /* 清场：删掉 UP2（本轮新增），并把它从画廊里摘掉，不给后续断言留脏数据 */
  const del2 = await page.evaluate(async name => {
    const res = await fetch(CONTENT_BASE + '/media/file/img/' + encodeURIComponent(name),
      { method: 'DELETE', headers: { Authorization: 'Bearer ' + sbToken() } });
    const j = await res.json().catch(() => ({}));
    const gal = edGet(ED.doc, ED.sub.concat(['images','usable'])) || [];
    const k = gal.indexOf(name);
    if (k >= 0) gal.splice(k, 1);
    const p0 = edGet(ED.doc, ED.sub) || {};
    if (p0.images && p0.images.hero === name) p0.images.hero = gal[0] || '';
    return { ok: !!(j && j.ok), status: res.status, galN: gal.length };
  }, UP2).catch(e => ({ ok: false, status: 0, err: String(e && e.message) }));
  await page.evaluate(async () => { await mediaLoad(); renderPickGrid(); });
  check('IMG6 清场：测试文件已删除且已摘出画廊', del2.ok && del2.galN === galBefore,
    'delete=' + JSON.stringify(del2) + ' galBefore=' + galBefore);

"""

s = s[:i] + new_img + s[j:]
io.open(F, 'w', encoding='utf-8').write(s)
print('  ✓ IMG 段已替换为真实路径版（IMG0–IMG6）')
print('OK · 020d 完成')
