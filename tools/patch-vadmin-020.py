# -*- coding: utf-8 -*-
"""
vadmin-020 · 上传的图「哪儿都看不到」——补上 R2 媒体库 → 型号图库(imagery) 的登记链

用户两次反馈「没有上传新图」。真根因（比 CORS 更贴近感受）：
  上传只写 R2 + 仓库 assets/img/，**不登记进 build/data/imagery.json**；
  而主图下拉选项、画廊缩略图、官网取图 URL 全部只认 imagery 图库
  ⇒ 图传上去了，后台里任何地方都找不到它（下拉里看不到、画廊显示「图库未匹配」、官网取不到 url）。

本补丁（前端 index.html，7 处）：
  ① 新辅助函数 edSku/imageryDoc/ensureInImagery/edThumbUrl
     · imageryDoc 在原文件未成功加载时**返回 null 拒绝写入**（绝不重建覆盖真源）
  ② 上传成功即把文件名登记进本型号 imagery 图库（src + url=/assets/img/<name>）
  ③ 缩略图回退：imagery 未命中但在媒体库 → 走 Worker R2 直读（不再「图库未匹配」灰框）
  ④ 主图下拉加「媒体库（刚上传，未加入画廊）」分组 → 打开下拉就能看到新图并选它
  ⑤ 保存草稿时一并提交 imagery.json（否则下拉有名字、官网取不到 url）
  ⑥ 上传完成横幅写明下一步；刚上传的图排弹层最前并标「刚上传」

断言锚点全部 count==1，失败即中止，不做「试着改改看」。
"""
import io, sys

F = 'index.html'
s = io.open(F, encoding='utf-8').read()
orig = s
n = 0

def rep(old, new, label, expect=1):
    global s, n
    c = s.count(old)
    assert c == expect, '[%s] 锚点命中 %d 次（期望 %d）: %r' % (label, c, expect, old[:90])
    s = s.replace(old, new)
    n += 1
    print('  ✓ %s' % label)

# ── ① 新增辅助函数（插在 edImgMap 之前）────────────────────────────────
rep(
"""function edImgMap(){""",
"""/* ── vadmin-020：让上传的图真的进「本型号图库」────────────────────
   为什么必须做：媒体库(R2) 与 型号图库(build/data/imagery.json) 是两套列表，
   而主图下拉、画廊缩略图、官网取图 URL **全部只认 imagery**。
   不登记 ⇒ 图传上去了，后台哪儿都看不到（下拉里没有、画廊「图库未匹配」、官网无 url）。 */
let ED_IMAGERY_DIRTY = false;
const JUST_UPLOADED = new Set();
const IMAGERY_PATH = 'build/data/imagery.json';
function edSku(){
  if (!ED || !ED.doc || ED.path !== 'data/products.json') return null;
  const p = edGet(ED.doc, ED.sub) || {};
  return p.sku ? String(p.sku) : null;
}
function imageryDoc(){
  /* ! 未成功加载（null）时**拒绝写入**：宁可登记失败，也绝不拿空对象覆盖真源图库 */
  const cur = STORE.files[IMAGERY_PATH];
  return (cur && typeof cur === 'object') ? cur : null;
}
function ensureInImagery(name){
  const sku = edSku();
  if (!sku || !name) return false;
  const doc = imageryDoc();
  if (!doc) return false;
  if (!doc[sku] || typeof doc[sku] !== 'object') doc[sku] = { items: [] };
  if (!Array.isArray(doc[sku].items)) doc[sku].items = [];
  if (doc[sku].items.some(it => it && it.src === name)) return false;
  doc[sku].items.push({ src: name, url: '/assets/img/' + name });
  ED_IMAGERY_DIRTY = true;
  return true;
}
/* 缩略图 URL：imagery 命中走官网域；未命中但刚上传过走 Worker 直读（R2）；都没有返回空 */
function edThumbUrl(fn, map){
  if (map && map[fn]) return imgSrc(map[fn], map[fn]);
  if (MEDIA_UPLOADED.has(fn)) return CONTENT_BASE + '/media/file/img/' + encodeURIComponent(fn);
  return '';
}
function edImgMap(){""",
'① 新增 imagery 登记辅助函数')

# ── ② edThumb 走回退 URL ────────────────────────────────────────────
rep(
"""function edThumb(fn, map, hero){
  const u = map[fn];
  if (!u) return '<div class="ed-thumb' + (hero ? ' hero' : '') + '"><span class="mono dim">' + esc(fn) + '<br>（图库未匹配）</span></div>';
  return '<div class="ed-thumb' + (hero ? ' hero' : '') + '"><img src="' + escAttr(imgSrc(u, u)) + '" loading="lazy" onerror="this.style.display=\\'none\\'"><span class="mono">' + esc(fn) + '</span></div>';
}""",
"""function edThumb(fn, map, hero){
  const u = edThumbUrl(fn, map);   /* vadmin-020：imagery 未命中但刚上传 → 回退 R2 直读 */
  if (!u) return '<div class="ed-thumb' + (hero ? ' hero' : '') + '"><span class="mono dim">' + esc(fn) + '<br>（图库未匹配）</span></div>';
  return '<div class="ed-thumb' + (hero ? ' hero' : '') + '"><img src="' + escAttr(u) + '" loading="lazy" onerror="this.style.display=\\'none\\'"><span class="mono">' + esc(fn) + '</span></div>';
}""",
'② edThumb 缩略图回退 R2')

# ── ③ edHeroStrip 走回退 URL（原来写死 IMG_BASE+u，刚上传的图必裂）────
rep(
"""    const u = map[fn], isHero = (fn === imgs.hero);
    return '<div class="ed-thumb' + (isHero ? ' hero' : '') + '">'
      + (u ? '<img src="' + escAttr(IMG_BASE + u) + '" loading="lazy" onerror="this.style.display=\\'none\\'">'
           : '<div class="ed-thumb-ph">图库未匹配</div>')""",
"""    const u = edThumbUrl(fn, map), isHero = (fn === imgs.hero);   /* vadmin-020：刚上传的图走 R2，别写死官网域 */
    return '<div class="ed-thumb' + (isHero ? ' hero' : '') + '">'
      + (u ? '<img src="' + escAttr(u) + '" loading="lazy" onerror="this.style.display=\\'none\\'">'
           : '<div class="ed-thumb-ph">图库未匹配</div>')""",
'③ edHeroStrip 主图条回退 R2')

# ── ④ 主图下拉加「媒体库（刚上传）」分组 ──────────────────────────────
rep(
"""  const heroOpts = usable.map(fn =>""",
"""  /* vadmin-020：媒体库里已登记进本型号图库、但还没加进画廊的图 ——
     让「打开主图下拉就能看到刚上传的图」成立（此前下拉只列已有画廊，用户永远找不到新图） */
  const extraOpts = Array.from(MEDIA_UPLOADED).filter(n =>
      /\\.(webp|jpe?g|png|avif|gif|svg)$/i.test(n) && usable.indexOf(n) < 0)
    .map(n => '<option value="' + escAttr(n) + '"' + (n === imgs.hero ? ' selected' : '') + '>' + esc(n) + '</option>').join('');
  const heroOpts = usable.map(fn =>""",
'④a 主图下拉：媒体库分组数据')

rep(
"""    + (heroOpts || '<option value="">（画廊为空）</option>') + '</select>'""",
"""    + (heroOpts ? '<optgroup label="本型号画廊">' + heroOpts + '</optgroup>' : '')
    + (extraOpts ? '<optgroup label="媒体库 · 刚上传（未加入画廊）">' + extraOpts + '</optgroup>' : '')
    + ((heroOpts || extraOpts) ? '' : '<option value="">（暂无图片，点右边「选图」上传）</option>') + '</select>'""",
'④b 主图下拉：分组渲染')

# ── ⑤ 上传成功即登记进型号图库 + 记「刚上传」──────────────────────────
rep(
"""      if (res.ok && j && j.ok){
        done.push(j.name || f.name);""",
"""      if (res.ok && j && j.ok){
        const upName = j.name || f.name;
        done.push(upName);
        JUST_UPLOADED.add(upName);
        /* vadmin-020：就地登记进本型号 imagery 图库 —— 否则主图下拉列不出、缩略图「图库未匹配」、官网取不到 url */
        ensureInImagery(upName);""",
'⑤ 上传成功即登记进型号图库')

# ── ⑥ 保存草稿时一并提交 imagery.json ────────────────────────────────
rep(
"""    await contentPut(ED.path, ED.doc, ED.message);
    STORE.files[ED.path] = JSON.parse(JSON.stringify(ED.doc));
    document.getElementById('edMsg').innerHTML = '<b style="color:var(--ok)">已保存到草稿（cms 分支）。</b>还没上线 —— 去「变更清单」过目后点发布。';""",
"""    await contentPut(ED.path, ED.doc, ED.message);
    STORE.files[ED.path] = JSON.parse(JSON.stringify(ED.doc));
    let extra = '';
    if (ED_IMAGERY_DIRTY){
      /* vadmin-020：新图登记在 imagery.json，必须一并提交，否则下拉有名字、官网取不到 url */
      const imgDoc = imageryDoc();
      if (imgDoc){
        await contentPut(IMAGERY_PATH, imgDoc, '后台：登记新上传图片到型号图库');
        ED_IMAGERY_DIRTY = false;
        extra = '（新图已登记进型号图库）';
      } else {
        extra = '（⚠ 图库文件未加载成功，新图未登记，请刷新页面重试）';
      }
    }
    document.getElementById('edMsg').innerHTML = '<b style="color:var(--ok)">已保存到草稿（cms 分支）。</b>' + extra + '还没上线 —— 去「变更清单」过目后点发布。';""",
'⑥ 保存草稿一并提交 imagery.json')

# ── ⑦ 上传完成横幅写明下一步；刚上传排最前并标「刚上传」──────────────
rep(
"""  const parts = [];
  if (done.length) parts.push('已上传 ' + done.length + ' 个：' + done.join('、'));""",
"""  const parts = [];
  if (done.length) parts.push('已上传 ' + done.length + ' 个：' + done.join('、')
    + (ED && ED.path === 'data/products.json'
       ? '（已登记进本型号图库 —— 点图片加入画廊，或直接在「主图」下拉里选它）' : ''));""",
'⑦a 上传完成横幅引导文案')

rep(
"""    out.push({ name:n, url: imgSrc(src, url), tag:'仓库图' });
  });
  return out;
}""",
"""    out.push({ name:n, url: imgSrc(src, url), tag:'仓库图' });
  });
  /* vadmin-020：刚上传的排最前（传完一眼就能看到并点它） */
  out.sort((a, b) => (JUST_UPLOADED.has(b.name) ? 1 : 0) - (JUST_UPLOADED.has(a.name) ? 1 : 0));
  out.forEach(it => { if (JUST_UPLOADED.has(it.name)) it.tag = '刚上传'; });
  return out;
}""",
'⑦b 刚上传的图排最前')

assert s != orig
io.open(F, 'w', encoding='utf-8').write(s)
print('\nOK · vadmin-020 完成 %d 处改动 · 字节 %d → %d' % (n, len(orig), len(s)))
