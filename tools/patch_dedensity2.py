#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vadmin-012b · 继续降噪：
① 数组的数组（面包屑 [["Home","/"],["Factory",null]]）→「行模式」：一层框、每行输入框横排，
   不再出现「项 0 → 0·2 项 → 项 0」三层套娃；
② 分区模式下省掉与分区标题重复的内层对象标题（「SEO 与分享卡片」下面不再出现「SEO 与分享卡片 META」）。
只改渲染，data-ed 路径与增删调序逻辑不变（edBlank 能复制二维数组，「插入一项」行为一致）。"""
import io, os

F = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'index.html'))
s = io.open(F, encoding='utf-8').read()

def rep(old, new, tag):
    global s
    assert s.count(old) == 1, '[%s] 出现 %d 处' % (tag, s.count(old))
    s = s.replace(old, new, 1)
    print('  ok  %s' % tag)

print('>>> 1) CSS：行内横排')
rep("""  .ed-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(216px,1fr));gap:0 18px}
  .ed-grid .ed-field{margin:7px 0}""",
"""  .ed-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(216px,1fr));gap:0 18px}
  .ed-grid .ed-field{margin:7px 0}
  /* 数组的数组行模式：一行多项横排（面包屑 = 行 [名称, 链接]） */
  .ed-inline{display:flex;gap:12px}
  .ed-inline .ed-field{flex:1;margin:4px 0 6px}""",
    '.ed-inline')

print('>>> 2) edNodeHTML：加 bare 参数（分区模式下省掉重复的内层标题）')
rep("""function edNodeHTML(path, v, keyLabel, sch, origKey){""",
    """function edNodeHTML(path, v, keyLabel, sch, origKey, bare){""",
    '签名')

rep("""    return '<div class="ed-obj"><div class="ed-obj-h">' + esc(keyLabel) + edKeyTag(keyLabel, origKey) + '</div>' + kids + '</div>';
  }""",
"""    /* bare：外层分区卡片已经标过这个名字了，内层不再重复一遍标题（只留内容） */
    return bare ? kids
      : '<div class="ed-obj"><div class="ed-obj-h">' + esc(keyLabel) + edKeyTag(keyLabel, origKey) + '</div>' + kids + '</div>';
  }""",
    '对象分支 bare')

print('>>> 3) 数组分支：行模式（数组的数组且内层全叶子）')
rep("""  if (Array.isArray(v)){
    const lp = escAttr(JSON.stringify(path));
    const items = v.map((it, i) => {""",
"""  if (Array.isArray(v)){
    const lp = escAttr(JSON.stringify(path));
    /* ── 行模式：数组的数组且内层全是叶子（面包屑 / 表格式数据）──
       一层框 + 每行横排，不再「项 → 数组 → 项」三层套娃；
       路径 data-ed 仍是 [.., i, j]，编辑与增删调序逻辑与通用数组完全一致。 */
    if (v.length && v.every(x => Array.isArray(x))
        && v.every(inner => inner.every(x => x === null || typeof x !== 'object'))){
      const opsRow = i => '<span class="ed-ops">'
        + '<button class="btn ghost" data-edop="up" data-edlist="' + lp + '" data-edi="' + i + '" title="上移">↑</button>'
        + '<button class="btn ghost" data-edop="down" data-edlist="' + lp + '" data-edi="' + i + '" title="下移">↓</button>'
        + '<button class="btn ghost" data-edop="dup" data-edlist="' + lp + '" data-edi="' + i + '">复制</button>'
        + '<button class="btn ghost risk" data-edop="del" data-edlist="' + lp + '" data-edi="' + i + '">删</button></span>';
      const rows = v.map((inner, i) =>
        '<div class="ed-item"><div class="ed-item-h">行 ' + (i + 1) + opsRow(i) + '</div><div class="ed-inline">'
        + inner.map((x, j) => '<label class="ed-field"><span class="ed-k">'
          + esc(ED_LABELS[String(j)] || String(j)) + '</span>'
          + edLeafHTML(path.concat(i, j), x) + '</label>').join('')
        + '</div></div>').join('');
      const addRow = '<button class="btn ghost sm" data-edop="add" data-edlist="' + lp + '">＋插入一行</button>';
      return '<div class="ed-obj"><div class="ed-arr-h">' + esc(keyLabel) + edKeyTag(keyLabel, origKey)
        + ' · ' + v.length + ' 行　' + addRow + '</div>'
        + (rows || '<div class="ed-ro">（空列表 —— 点「插入一行」新增）</div>') + '</div>';
    }
    const items = v.map((it, i) => {""",
    '行模式')

print('>>> 4) edSectionsHTML：分区模式下对象子键传 bare（数组不 bare —— 插入按钮要在）')
rep("""    const inner = edNodeHTML(path.concat(k), obj[k], lab, subSch, k);
    secs += asSec ? edSec(lab, ED_SEC_NOTE[k] || '', inner) : inner;""",
"""    const isObj = obj[k] && typeof obj[k] === 'object' && !Array.isArray(obj[k]);
    const inner = edNodeHTML(path.concat(k), obj[k], lab, subSch, k, /*bare=*/ asSec && isObj);
    secs += asSec ? edSec(lab, ED_SEC_NOTE[k] || '', inner) : inner;""",
    'bare 传递')

io.open(F, 'w', encoding='utf-8').write(s)
print('完成')
