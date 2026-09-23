#!/usr/bin/env python3
"""vadmin-008：编辑器改「字段白名单」模式。
人该改的文案字段才出现（带中文标签 + 原键名注记）；
hide/deny 的系统识别字段整段隐藏（只留一条计数提示）；
`_` 前缀键一律隐藏；sku/slug 等结构键只读；imagery.json 整文件锁定。
"""
import io, os, sys

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'index.html')
s = io.open(P, encoding='utf-8').read()

def rep(old, new, tag, n=1):
    global s
    c = s.count(old)
    assert c == n, '[%s] 断言失败：出现 %d 次（期望 %d）' % (tag, c, n)
    s = s.replace(old, new)
    print('OK [%s]' % tag)

# ── 1. edNodeHTML：对象分支改为白名单渲染 + 新签名 (path, v, keyLabel, sch, origKey)
rep("""function edNodeHTML(path, v, keyLabel){
  if (v && typeof v === 'object' && !Array.isArray(v)){
    const kids = Object.keys(v).map(k => {
      if (k.startsWith('_')) return '<div class="ed-ro" title="' + escAttr(String(v[k]).slice(0,200)) + '">' + esc(k) + ' · ' + esc(String(v[k]).slice(0,90)) + '</div>';
      return edNodeHTML(path.concat(k), v[k], k);
    }).join('');
    return '<div class="ed-obj"><div class="ed-obj-h">' + esc(keyLabel) + '</div>' + kids + '</div>';
  }""",
"""/* 字段白名单（vadmin-008）：fields=人该改的文案（中文标签）；ro=结构键只读；hide/deny=系统识别字段整段隐藏。
   `_` 前缀键一律隐藏。没有 schema 的文件保持通用渲染，但 `_` 键同样隐藏。 */
const ED_SCHEMA = {
  'data/products.json': {
    itemOf: 'products',
    fields: {
      nameZh: '中文名', nameEn: '英文名', tagline: '一句话卖点（英文）',
      deviceType: '产品形态（英文）', moq: '最小起订量', leadTime: '交期（工作日天数）',
      warranty: '质保（英文）', packages: '包装 · 实际交运纸箱一套', specs: '规格参数（参数名别改，只改值）'
    },
    ro: { sku: '型号', category: '所属分类' },
    hide: ['nameEnStatus','categoryNote','note','status','certificationGroup','contraindication','copyRules','images'],
    hideLabel: '英文备注 / 图片清单 / 合规规则等'
  },
  'build/data/insights.json': {
    itemOf: 'notes',
    fields: {
      title: '标题', card: '列表卡片摘要', cardAlt: '卡片图 alt 文本', lede: '导语',
      alt: '正文配图 alt 文本', date: '发布日期', readMins: '预计阅读（分钟）', blocks: '正文块（可增删 / 复制 / 调序）'
    },
    ro: { slug: 'slug（链接标识）', ix: '编号', status: '发布状态' },
    hide: ['image','cardW','cardH'],
    hideLabel: '配图文件名 / 尺寸标记'
  },
  'build/data/imagery.json': {
    locked: true,
    hideLabel: '全站图片资产清单（文件名与落位）—— 系统识别用，不在页面上编辑。'
  }
};
const PAGES_SCHEMA = { deny: ['pvbar'], hideLabel: '预览条等内部字段' };
function edSchemaFor(path, sub){
  const s = ED_SCHEMA[path] || (path.indexOf('content/pages/') === 0 ? PAGES_SCHEMA : null);
  if (!s) return null;
  if (s.locked) return s;
  if (s.itemOf) return (sub && sub[0] === s.itemOf) ? s : null;
  return (sub && sub.length) ? null : s;
}
const edKeyTag = (label, key) => (key && key !== label) ? ' <span class="mono dim">' + esc(key) + '</span>' : '';
function edNodeHTML(path, v, keyLabel, sch, origKey){
  if (v && typeof v === 'object' && !Array.isArray(v)){
    const S = sch || {};
    const hide = S.hide || [], deny = S.deny || [], F = S.fields || {}, R = S.ro || {};
    let hiddenN = 0;
    const kids = Object.keys(v).map(k => {
      if (hide.indexOf(k) >= 0 || deny.indexOf(k) >= 0 || k.charAt(0) === '_'){ hiddenN++; return ''; }
      if (R[k])
        return '<div class="ed-ro" title="结构键：改动会牵动页面链接与归组，只读">' + esc(F[k] || R[k]) + ' · <span class="mono">' + esc(String(v[k]).slice(0,60)) + '</span> · 只读</div>';
      return edNodeHTML(path.concat(k), v[k], F[k] || k, null, k);
    }).join('')
      + (hiddenN ? '<div class="ed-ro">🔒 已隐藏 ' + hiddenN + ' 个内部字段' + (S.hideLabel ? '（' + esc(S.hideLabel) + '）' : '') + '—— 系统识别用，不在页面编辑。</div>' : '');
    return '<div class="ed-obj"><div class="ed-obj-h">' + esc(keyLabel) + edKeyTag(keyLabel, origKey) + '</div>' + kids + '</div>';
  }""", 'edNodeHTML 对象分支')

# ── 2. 数组表头：带原键名注记
rep("""    return '<div class="ed-obj"><div class="ed-arr-h">' + esc(keyLabel) + ' · ' + v.length + ' 项　' + add + '</div>'""",
"""    return '<div class="ed-obj"><div class="ed-arr-h">' + esc(keyLabel) + edKeyTag(keyLabel, origKey) + ' · ' + v.length + ' 项　' + add + '</div>'""", '数组表头')

# ── 3. edRender：传入 schema
rep("document.getElementById('edBody').innerHTML = edNodeHTML(ED.sub, edGet(ED.doc, ED.sub), ED.sub.length ? String(ED.sub[ED.sub.length - 1]) : ED.path);",
    "document.getElementById('edBody').innerHTML = edNodeHTML(ED.sub, edGet(ED.doc, ED.sub), ED.sub.length ? String(ED.sub[ED.sub.length - 1]) : ED.path, edSchemaFor(ED.path, ED.sub));",
    'edRender 传 schema')

# ── 4. openEd：锁定文件直接拦
rep("""  if (!STORE.files[path]){ alert('这份内容还没读到，无法编辑。请先回总览确认真源读取正常。'); return }
  ED = { path, sub: sub || [], label: label || path,""",
"""  if (!STORE.files[path]){ alert('这份内容还没读到，无法编辑。请先回总览确认真源读取正常。'); return }
  const s0 = edSchemaFor(path, sub || []);
  if (s0 && s0.locked){ alert(s0.hideLabel || '该文件为系统识别用，不在页面上编辑。'); return }
  ED = { path, sub: sub || [], label: label || path,""", 'openEd 锁定拦截')

# ── 5. 产品页「怎么改」提示同步（别让页面说谎）
rep("""      点行尾「改」进入编辑器：<strong>文案值随便改</strong>（名称、卖点、MOQ、交期、质保……）；
      <strong>结构键动前想清楚</strong> —— sku / slug / category 牵动页面链接与归组，status 是数据完备度标记不是上架开关。
      保存进的是草稿，「变更清单」过目后发布才上线。""",
"""      点行尾「改」进入编辑器：<strong>只出现人该改的文案字段</strong>（名称、卖点、MOQ、交期、质保、规格值……）；
      内部字段（英文备注 / 图片清单 / 合规规则等）<strong>已整体隐藏</strong>，不会被误改；sku / category 等结构键只读。
      保存进的是草稿，「变更清单」过目后发布才上线。""", '产品页提示')

io.open(P, 'w', encoding='utf-8').write(s)
print('补丁完成')
