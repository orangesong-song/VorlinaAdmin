#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vadmin-010 · 产品模块 Everchill 式改造（只改前端 index.html，不动 Worker）
  1) 产品列表：表格 → 卡片流（缩略图 + SKU + 中文名 + 分类 + 状态点 + 「改」）
  2) 单品编辑：字段平铺 → 分区表单（基础信息 / 型号分类只读 / 包装 / 规格 / 图片）
  3) 图片区：主图用下拉从图库选 + 缩略图「设为主图」一键切换

⚠️ NAS(smbfs) 上 Edit 工具会误报 modified，统一用本脚本 + 每处断言出现次数。
"""
import io, sys, os

F = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'index.html')
F = os.path.abspath(F)
src = io.open(F, encoding='utf-8').read()
orig = src
n = 0


def rep(old, new, times=1, tag=''):
    global src, n
    c = src.count(old)
    assert c == times, '[%s] 锚点命中 %d 次，预期 %d 次' % (tag or old[:40], c, times)
    src = src.replace(old, new, times)
    n += 1
    print('  ok  %-28s (%d 处)' % (tag or old[:38].replace('\n', '⏎'), times))


print('patch →', F)

# ── 1. CSS：产品卡片 + 分区表单 ──────────────────────────────
rep(
    "  .ed-msg{padding:10px 20px;",
    """  .pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(232px,1fr));gap:14px;padding:14px}
  .pcard{border:1px solid var(--line);background:#fff;display:flex;flex-direction:column}
  .pcard-thumb{height:148px;background:#F5F3EF;display:flex;align-items:center;justify-content:center;overflow:hidden;border-bottom:1px solid var(--line)}
  .pcard-thumb img{max-width:100%;max-height:100%;object-fit:contain;display:block}
  .pcard-b{padding:11px 13px;flex:1}
  .pcard-sku{font-family:var(--mono);font-size:11px;letter-spacing:.1em;color:var(--muted)}
  .pcard-name{font-size:14px;line-height:1.45;margin:5px 0 6px;color:var(--ink)}
  .pcard-meta{font-size:12px;color:var(--muted)}
  .pcard-f{display:flex;align-items:center;gap:8px;padding:9px 13px;border-top:1px solid var(--line)}
  .pcard-f .grow{margin-left:auto}
  .pcard-empty{padding:20px;font-size:13px;color:var(--muted)}
  .edsec{border:1px solid var(--line);margin:10px 0;background:#fff}
  .edsec-h{font-family:var(--mono);font-size:11px;letter-spacing:.12em;color:var(--muted);text-transform:uppercase;padding:9px 12px;border-bottom:1px solid var(--line);background:rgba(0,0,0,.03)}
  .edsec-b{padding:10px 13px 13px}
  .edsec-note{font-size:12px;color:var(--muted);margin:0 0 9px}
  .ed-thumb-ph{height:56px;display:flex;align-items:center;justify-content:center;font-size:10px;color:var(--muted)}
  .ed-thumb .btn{margin:3px 2px 2px;width:100%}
  .ed-msg{padding:10px 20px;""",
    tag='CSS 卡片与分区样式'
)

# ── 2. 产品列表：表格 → 卡片流 ──────────────────────────────
rep(
    """    const prodRows = prods.map((p, i) => row(
      [esc(p.sku), esc(p.nameEn), esc(catName(p.category)),
       String(p.status || '').toUpperCase() === 'OK' ? ['ok', '已发布'] : ['draft', (p.status || '未标状态')],
       p.moq == null ? '-' : String(p.moq),
       pr ? edBtn('data/products.json', ['products', i], '产品 · ' + (p.sku || i)) : '-'],
      { kAt:[0], dotAt:3, numAt:4 })).join('');""",
    """    const prodCards = prods.map((p, i) => {
      const ok = String(p.status || '').toUpperCase() === 'OK';
      const u = prodHeroUrl(p);
      return '<div class="pcard">'
        + '<div class="pcard-thumb">' + (u
            ? '<img src="' + escAttr(u) + '" loading="lazy" alt="">'
            : '<span class="mono dim" style="font-size:11px">无图</span>') + '</div>'
        + '<div class="pcard-b">'
        +   '<div class="pcard-sku">' + esc(p.sku || '-') + '</div>'
        +   '<div class="pcard-name">' + esc(p.nameZh || p.nameEn || '-') + '</div>'
        +   '<div class="pcard-meta">' + esc(catName(p.category)) + ' · MOQ ' + (p.moq == null ? '-' : esc(String(p.moq)))
        +     (p.leadTime ? ' · 交期 ' + esc(String(p.leadTime)) : '') + '</div>'
        + '</div>'
        + '<div class="pcard-f"><span class="dot ' + (ok ? 'ok' : 'draft') + '">'
        +   (ok ? '已发布' : esc(p.status || '未标状态')) + '</span><span class="grow"></span>'
        +   (pr ? edBtn('data/products.json', ['products', i], '产品 · ' + (p.sku || i)) : '-')
        + '</div></div>';
    }).join('');""",
    tag='产品卡片数据'
)

rep(
    """    <div class="panel sec">
      <div class="panel-h"><span class="ttl">型号 · ${prods.length}</span></div>
      <table class="tbl">${head(['SKU','型号名称','分类','数据状态','MOQ','编辑'],[4])}
        <tbody>${prodRows || '<tr><td colspan="6" class="empty">读不到产品数据</td></tr>'}</tbody>
      </table>
    </div>""",
    """    <div class="panel sec">
      <div class="panel-h"><span class="ttl">型号 · ${prods.length}</span><span class="grow"></span>
        <span class="mono dim" style="font-size:11px">点卡片右下角「改」进分区表单</span></div>
      <div class="pgrid">${prodCards || '<div class="pcard-empty">读不到产品数据</div>'}</div>
    </div>""",
    tag='产品面板改卡片流'
)

rep(
    """      点行尾「改」进入编辑器：<strong>只出现人该改的文案字段</strong>（名称、卖点、MOQ、交期、质保、规格值……）；
      内部字段（英文备注 / 图片清单 / 合规规则等）<strong>已整体隐藏</strong>，不会被误改；sku / category 等结构键只读。""",
    """      点卡片右下角「改」进入<strong>分区表单</strong>：① 基础信息 ② 型号与分类（只读）③ 包装 ④ 规格参数 ⑤ 图片。
      运营只填格子；内部字段（英文备注 / 合规规则等）<strong>已整体隐藏</strong>，不会被误改；sku / category 等结构键只读。""",
    tag='产品页说明文案同步'
)

# ── 3. 取图工具 + 分区表单渲染 ──────────────────────────────
rep(
    "function edNodeHTML(path, v, keyLabel, sch, origKey){",
    """/* 某型号的主图 URL：imagery 图库按 sku 归组，hero 优先，取不到退回画廊第一张 */
function prodImgMap(sku){
  const out = {};
  const img = STORE.files['build/data/imagery.json'];
  if (img && sku && img[sku] && img[sku].items) for (const it of img[sku].items) out[it.src] = it.url;
  return out;
}
function prodHeroUrl(p){
  const map = prodImgMap(p && p.sku);
  const im = (p && p.images) || {};
  const fn = im.hero || ((im.usable || [])[0]);
  const u = fn ? map[fn] : '';
  return u ? IMG_BASE + u : '';
}
/* ── 产品分区表单（vadmin-010）──────────────────────────────
   白名单字段按「运营看得懂的分区」分组；数组 / 嵌套对象仍复用通用 edNodeHTML，
   保证 增 / 删 / 调序 / 复制 的操作与保存路径完全一致（一份逻辑，不写第二套）。 */
function edFieldRow(path, label, origKey, val){
  return '<label class="ed-field"><span class="ed-k">' + esc(label) + edKeyTag(label, origKey) + '</span>'
    + edLeafHTML(path, val) + '</label>';
}
function edArea(path, val, rows){
  return '<textarea class="ed-in" rows="' + (rows || 3) + '" data-ed="' + escAttr(JSON.stringify(path)) + '">'
    + esc(val == null ? '' : String(val)) + '</textarea>';
}
function edSec(title, note, body){
  return '<div class="edsec"><div class="edsec-h">' + esc(title) + '</div><div class="edsec-b">'
    + (note ? '<div class="edsec-note">' + note + '</div>' : '') + body + '</div></div>';
}
function edHeroStrip(imgs){
  const map = edImgMap();
  const list = (imgs.usable || []).slice();
  if (imgs.hero && list.indexOf(imgs.hero) < 0) list.unshift(imgs.hero);
  return '<div class="ed-thumb-row">' + list.map(fn => {
    const u = map[fn], isHero = (fn === imgs.hero);
    return '<div class="ed-thumb' + (isHero ? ' hero' : '') + '">'
      + (u ? '<img src="' + escAttr(IMG_BASE + u) + '" loading="lazy" onerror="this.style.display=\\'none\\'">'
           : '<div class="ed-thumb-ph">图库未匹配</div>')
      + '<span class="mono">' + esc(fn) + '</span>'
      + (isHero ? '<span class="mono" style="font-size:9px;color:var(--gold-ink)">当前主图</span>'
                : '<button class="btn ghost sm" data-hero="' + escAttr(fn) + '">设为主图</button>')
      + '</div>';
  }).join('') + '</div>';
}
function edProductHTML(){
  const S = ED_SCHEMA['data/products.json'];
  const base = ED.sub;                                  // ['products', i]
  const p = edGet(ED.doc, base) || {};
  const F = S.fields, R = S.ro;
  const basics = ['nameZh','nameEn','deviceType','moq','leadTime','warranty']
    .map(k => edFieldRow(base.concat(k), F[k], k, p[k])).join('')
    + '<label class="ed-field"><span class="ed-k">' + esc(F.tagline) + edKeyTag(F.tagline, 'tagline') + '</span>'
    + edArea(base.concat('tagline'), p.tagline, 3) + '</label>';
  const ro = Object.keys(R).map(k =>
    '<div class="ed-ro" title="结构键：改动会牵动页面链接与归组，只读">' + esc(R[k]) + ' · <span class="mono">'
    + esc(String(p[k] == null ? '' : p[k]).slice(0,60)) + '</span> · 只读</div>').join('');
  const imgs = p.images || {};
  const usable = imgs.usable || [];
  const heroOpts = usable.map(fn =>
    '<option value="' + escAttr(fn) + '"' + (fn === imgs.hero ? ' selected' : '') + '>' + esc(fn) + '</option>').join('');
  const imgBody = '<label class="ed-field"><span class="ed-k">主图 · 从本型号图库里选</span>'
    + '<select class="ed-in" data-ed="' + escAttr(JSON.stringify(base.concat(['images','hero']))) + '">'
    + (heroOpts || '<option value="">（画廊为空）</option>') + '</select></label>'
    + '<div class="edsec-note">缩略图取自 imagery 图库；点「设为主图」立即切换（仍需保存草稿）。</div>'
    + edHeroStrip(imgs)
    + edNodeHTML(base.concat(['images','usable']), usable, '画廊图片（文件名列表）',
                 (S.sub && S.sub.images) ? S.sub.images : null, 'usable');
  return edSec('① 基础信息', '', basics)
    + edSec('② 型号与分类 · 只读', '改 sku / category 会牵动页面链接与归组，需要改请找管理员。', ro)
    + edSec('③ 包装 · 实际交运纸箱', '只列买家实际收到的一套；内部层级不出现在页面上。',
            edNodeHTML(base.concat('packages'), p.packages || [], '包装清单', null, 'packages'))
    + edSec('④ 规格参数', '参数名固定，只改右边的值。',
            edNodeHTML(base.concat('specs'), p.specs || {}, '规格', null, 'specs'))
    + edSec('⑤ 图片', '主图与画廊都取自本型号的 imagery 图库。', imgBody)
    + '<div class="ed-ro">🔒 已隐藏 ' + (S.hide || []).length + ' 个内部字段（' + esc(S.hideLabel || '')
    + '）—— 系统识别用，不在页面编辑。</div>';
}
function edNodeHTML(path, v, keyLabel, sch, origKey){""",
    tag='分区表单函数组'
)

# ── 4. edRender 接线 ───────────────────────────────────────
rep(
    """  document.getElementById('edBody').innerHTML = edNodeHTML(ED.sub, edGet(ED.doc, ED.sub), ED.sub.length ? String(ED.sub[ED.sub.length - 1]) : ED.path, edSchemaFor(ED.path, ED.sub));""",
    """  const isProd = (ED.path === 'data/products.json' && ED.sub[0] === 'products');
  document.getElementById('edBody').innerHTML = isProd
    ? edProductHTML()
    : edNodeHTML(ED.sub, edGet(ED.doc, ED.sub), ED.sub.length ? String(ED.sub[ED.sub.length - 1]) : ED.path, edSchemaFor(ED.path, ED.sub));""",
    tag='edRender 接线'
)

# ── 5. 「设为主图」点击处理 ─────────────────────────────────
rep(
    """  if (!ED) return;
  const opBtn = e.target.closest('[data-edop]');""",
    """  if (!ED) return;
  const heroBtn = e.target.closest('[data-hero]');
  if (heroBtn){ edSet(ED.doc, ED.sub.concat(['images','hero']), heroBtn.dataset.hero); edRender(); return }
  const opBtn = e.target.closest('[data-edop]');""",
    tag='设为主图按钮'
)

assert src != orig, '没有任何改动'
io.open(F, 'w', encoding='utf-8').write(src)
print('\n完成：%d 处替换，写入 %s（%d 字节）' % (n, F, len(src.encode('utf-8'))))
