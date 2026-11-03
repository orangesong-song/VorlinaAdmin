# -*- coding: utf-8 -*-
"""vadmin-023b：正文块的第二轮打磨（实拍发现的问题）。

1. 表格单元格 / 列表条目用单行 input ⇒ 长句被横向截断，看不见也改不全。
   改为按内容长度自动定行的 textarea（1–5 行），竖着能看全。
2. 提示块标签写着「内容 V」「小标题 B」—— V/B 是 JSON 键名，运营看不懂，改成中文。
3. ① 基本信息 6 个字段全宽竖排，进正文要滚很久；日期 + 阅读分钟 并排放。
"""
import io

F = 'index.html'
s = io.open(F, encoding='utf-8').read()


def rep(old, new, why=''):
    global s
    c = s.count(old)
    assert c == 1, '锚点命中 %d 次（期望 1）%s: %r' % (c, why, old[:80])
    s = s.replace(old, new, 1)


# ── ① 自动行高助手 + 单元格/列表改用 textarea ────────────────
rep("""function nbOps(listAttr, i){""",
    """/* 按内容长度算行高：表格单元格与列表条目常有整句，单行 input 会把它截掉半句 */
function nbAutoRows(v, perLine, max){
  const t = String(v == null ? '' : v);
  let n = 0;
  t.split('\\n').forEach(function (l){ n += Math.max(1, Math.ceil(l.length / perLine)) });
  return Math.min(max || 5, Math.max(1, n));
}
function nbOps(listAttr, i){""",
    'nbAutoRows')

# 列表条目
rep("""        return '<div class="nb-line"><span class="nb-rn">' + (j + 1) + '</span>'
          + '<input class="ed-in" data-ed="' + pAttr(vp.concat(j)) + '" value="' + escAttr(line) + '">'
          + nbLineOps(lp, j, false) + '</div>';""",
    """        return '<div class="nb-line"><span class="nb-rn">' + (j + 1) + '</span>'
          + '<textarea class="ed-in nb-cell" rows="' + nbAutoRows(line, 72, 4) + '"'
          + ' data-ed="' + pAttr(vp.concat(j)) + '">' + esc(line) + '</textarea>'
          + nbLineOps(lp, j, false) + '</div>';""",
    '列表条目改 textarea')

# 表头单元格
rep("""            return '<input class="ed-in" data-ed="' + pAttr(vp.concat('head', j)) + '" value="' + escAttr(h)
              + '" placeholder="列 ' + (j + 1) + '">';""",
    """            return '<textarea class="ed-in nb-cell nb-cellh" rows="1" data-ed="' + pAttr(vp.concat('head', j))
              + '" placeholder="列 ' + (j + 1) + '">' + esc(h) + '</textarea>';""",
    '表头改 textarea')

# 数据单元格
rep("""              return '<input class="ed-in" data-ed="' + pAttr(vp.concat('rows', j, k)) + '" value="' + escAttr(c) + '">';""",
    """              return '<textarea class="ed-in nb-cell" rows="' + nbAutoRows(c, 26, 5) + '"'
                + ' data-ed="' + pAttr(vp.concat('rows', j, k)) + '">' + esc(c) + '</textarea>';""",
    '数据单元格改 textarea')

# 提示块标签去内部键名
rep("""        + '<label class="ed-field"><span class="ed-k">语调 tone</span>'""",
    """        + '<label class="ed-field"><span class="ed-k">样式</span>'""",
    '提示块 tone 标签')
rep("""        + '<label class="ed-field"><span class="ed-k">小标题 b</span>'""",
    """        + '<label class="ed-field"><span class="ed-k">小标题（加粗那半句）</span>'""",
    '提示块 b 标签')
rep("""        + '<label class="ed-field"><span class="ed-k">内容 v</span>'""",
    """        + '<label class="ed-field"><span class="ed-k">内容</span>'""",
    '提示块 v 标签')

# ── ② 基本信息：日期 + 阅读分钟 并排 ─────────────────────────
rep("""    + ['date','readMins'].map(k => edFieldRow(base.concat(k), L(k), k, n[k])).join('');""",
    """    + '<div class="ed-two">'
    + ['date','readMins'].map(k => edFieldRow(base.concat(k), L(k), k, n[k])).join('')
    + '</div>';""",
    '基本信息两列')

# ── ③ CSS：单元格 textarea + 两列行 ──────────────────────────
rep("""  .nb-cells .ed-in{padding:5px 7px;font-size:12px;min-width:0}""",
    """  .nb-cells .ed-in{padding:5px 7px;font-size:12px;min-width:0;flex:1;line-height:1.5}
  .nb-cell{resize:vertical}
  .nb-cellh{font-weight:600;background:#fff}
  .ed-two{display:flex;gap:16px}
  .ed-two .ed-field{flex:1;min-width:0}""",
    '单元格 CSS')

io.open(F, 'w', encoding='utf-8').write(s)
print('✓ vadmin-023b 全部命中')
