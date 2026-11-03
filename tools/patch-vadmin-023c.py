# -*- coding: utf-8 -*-
"""vadmin-023c：正文块「全部收起 / 全部展开」+ 长文扫描。

24 块的文章即便平铺也还是很长，运营想"看一眼结构"时只能一路滚。
收起后每块只剩一行标题 + 类型 + 摘要，等价于一份目录。
"""
import io

F = 'index.html'
s = io.open(F, encoding='utf-8').read()


def rep(old, new, why=''):
    global s
    c = s.count(old)
    assert c == 1, '锚点命中 %d 次（期望 1）%s: %r' % (c, why, old[:80])
    s = s.replace(old, new, 1)


# 工具条右侧加「全部收起 / 全部展开」
rep("""  const addBar = '<div class="nb-add" data-nbpath="' + bpAttr + '"><span class="nb-addl">新块</span>'
    + Object.keys(NB_TYPES).map(t =>
        '<button class="btn ghost sm" data-nbadd="' + t + '">＋ ' + NB_TYPES[t] + '</button>').join('')
    + '</div>';""",
    """  const addBar = '<div class="nb-add" data-nbpath="' + bpAttr + '"><span class="nb-addl">新块</span>'
    + Object.keys(NB_TYPES).map(t =>
        '<button class="btn ghost sm" data-nbadd="' + t + '">＋ ' + NB_TYPES[t] + '</button>').join('')
    + '<span class="nb-spacer"></span>'
    + '<button class="btn ghost sm" data-nbfoldall="1" title="只留标题行，当目录看">全部收起</button>'
    + '<button class="btn ghost sm" data-nbfoldall="0">全部展开</button>'
    + '</div>';""",
    '全部收起按钮')

rep("""  const nbFold = e.target.closest('[data-nbfold]');""",
    """  const nbAll = e.target.closest('[data-nbfoldall]');
  if (nbAll){
    const fold = nbAll.dataset.nbfoldall === '1';
    document.querySelectorAll('#edBody .nb').forEach(function (x){
      x.classList.toggle('folded', fold);
      const t = x.querySelector('.nb-tog');
      if (t) t.textContent = fold ? '＋' : '−';
    });
    return;
  }
  const nbFold = e.target.closest('[data-nbfold]');""",
    '全部收起事件')

rep("""  .nb-addl{font-family:var(--mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-right:2px}""",
    """  .nb-addl{font-family:var(--mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-right:2px}
  .nb-spacer{flex:1;min-width:8px}""",
    'spacer CSS')

io.open(F, 'w', encoding='utf-8').write(s)
print('✓ vadmin-023c 全部命中')
