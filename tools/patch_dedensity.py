#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vadmin-012 · 编辑器降噪：分区卡片是唯一的框
用户反馈（2026-09-23 15:00）：「分区框太多，一块叠一块，一眼看不到重点」。
根因：ed-obj / ed-item 每层都画边框 —— 面包屑（数组→对象→数组→对象）渲染成四层套娃。
修法两条：
  ① 全叶子对象（面包屑项 / SEO meta / 规格参数）不再套框，排成紧凑网格；
  ② ed-obj 去边框改左侧细引导线，ed-item 边框压淡 —— 让分区卡片成为唯一的视觉主角。
data-ed 路径、增删调序、隐藏/只读判据一律不变（只改视觉，不动数据流）。
"""
import io, os

F = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'index.html'))
s = io.open(F, encoding='utf-8').read()
n0 = len(s)

def rep(old, new, tag, cnt=1):
    global s
    assert s.count(old) == cnt, '[%s] 期望 %d 处，实际 %d 处' % (tag, cnt, s.count(old))
    s = s.replace(old, new, cnt)
    print('  ok  %s' % tag)

print('>>> 1) CSS：内层去边框 / 网格 / 分区头加重')
rep("  .ed-obj{border:1px solid var(--line);padding:8px 14px 10px;margin:8px 0}",
    "  /* 内层结构不再画框：每画一层框就多一层噪音（运营反馈「一块叠一块」）—— 改左侧引导线 */\n"
    "  .ed-obj{border:0;border-left:2px solid rgba(21,22,26,.13);padding:2px 0 2px 12px;margin:6px 0;background:transparent}",
    'ed-obj 去边框')

rep("  .ed-item{border:1px solid var(--line);padding:6px 12px 8px;margin:8px 0;background:var(--card)}",
    "  /* 数组项保留边界感（它是可增删/调序的单位），但压淡、收紧 */\n"
    "  .ed-item{border:1px solid rgba(21,22,26,.13);padding:3px 11px 6px;margin:6px 0;background:rgba(255,255,255,.72)}",
    'ed-item 压淡')

rep("""  .edsec.folded .edsec-b{display:none}""",
"""  .edsec.folded .edsec-b{display:none}
  /* 简单键值对一行排：面包屑项 / SEO meta / 规格参数这类「全叶子对象」不再套子框 */
  .ed-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(216px,1fr));gap:0 18px}
  .ed-grid .ed-field{margin:7px 0}
  /* 分区头是唯一的「实框」，加重一点把层级压回来 */
  .edsec{margin:12px 0}
  .edsec-h{background:rgba(21,22,26,.055);font-size:12px;letter-spacing:.08em}""",
    '网格与分区头')

print('>>> 2) edNodeHTML：全叶子对象走紧凑网格')
rep("""function edNodeHTML(path, v, keyLabel, sch, origKey){
  if (v && typeof v === 'object' && !Array.isArray(v)){
    const S = sch || {};
    const hide = S.hide || [], deny = S.deny || [], F = S.fields || {}, R = S.ro || {};
    let hiddenN = 0;
    const kids = Object.keys(v).map(k => {""",
"""/* 全叶子对象：键对应的值全是字符串 / 数字 / 布尔 / null，且键数在 10 个以内。
   这类对象（面包屑的 {0,1}、SEO meta、规格参数）再套一层框纯属噪音 —— 直接排网格。 */
function edIsLeafObj(v){
  const ks = Object.keys(v);
  if (!ks.length || ks.length > 10) return false;
  return ks.every(k => {
    const x = v[k];
    return x === null || typeof x === 'string' || typeof x === 'number' || typeof x === 'boolean';
  });
}
function edNodeHTML(path, v, keyLabel, sch, origKey){
  if (v && typeof v === 'object' && !Array.isArray(v)){
    const S = sch || {};
    const hide = S.hide || [], deny = S.deny || [], F = S.fields || {}, R = S.ro || {};
    let hiddenN = 0;
    /* ── 紧凑分支：全叶子对象 —— 同样的 hide / deny / ro 判据，只换渲染容器 ── */
    if (edIsLeafObj(v)){
      const cells = [];
      for (const k of Object.keys(v)){
        if (hide.indexOf(k) >= 0 || deny.indexOf(k) >= 0 || k.charAt(0) === '_'){ hiddenN++; continue }
        const lab = F[k] || ED_LABELS[k] || k;
        if (R[k]){ cells.push(edRoRow(F[k] || R[k], v[k])); continue }
        cells.push('<label class="ed-field"><span class="ed-k">' + esc(lab) + edKeyTag(lab, k) + '</span>'
          + edLeafHTML(path.concat(k), v[k]) + '</label>');
      }
      return '<div class="ed-grid">' + cells.join('') + '</div>'
        + (hiddenN ? '<div class="ed-ro">🔒 已隐藏 ' + hiddenN + ' 个内部字段'
            + (S.hideLabel ? '（' + esc(S.hideLabel) + '）' : '') + ' —— 系统识别用，不在页面编辑。</div>' : '');
    }
    const kids = Object.keys(v).map(k => {""",
    '叶子网格分支')

io.open(F, 'w', encoding='utf-8').write(s)
print('\n写完：%d → %d 字符' % (n0, len(s)))
