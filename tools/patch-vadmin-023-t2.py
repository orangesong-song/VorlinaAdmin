# -*- coding: utf-8 -*-
"""修 verify-content 的 T2：数字断言被 textContent 粘连骗了。

现象：T2 报红（detail 为空），但页面实际正确。
真因：`/\\b16\\b/` 对 `#view.textContent` 判断，而 textContent 会把
「产品」「16」「6 个分类」连成 `产品166 个分类` ⇒ 16 后面紧跟 6，没有词边界。
修法：按 DOM 结构（.metric 的 k/v/d）取值，并直接与真源篇数比数。
"""
import io

F = 'tools/verify-content.js'
s = io.open(F, encoding='utf-8').read()


def rep(old, new):
    global s
    c = s.count(old)
    assert c == 1, '锚点命中 %d 次（期望 1）: %r' % (c, old[:70])
    s = s.replace(old, new, 1)


rep("""      nav: (document.querySelector('#railNav [aria-current="page"]') || {}).textContent || '',
    }));""",
    """      nav: (document.querySelector('#railNav [aria-current="page"]') || {}).textContent || '',
      /* 指标按 DOM 结构取 —— 不要在整页 textContent 里正则找数字：
         「产品16」+「6 个分类」会连成 166，\\b16\\b 永远失配（2026-11-03 T2 就这样红了一次）。 */
      metrics: [...document.querySelectorAll('#view .metric')].map(m => ({
        k: (m.querySelector('.k') || {}).textContent || '',
        v: (m.querySelector('.v') || {}).textContent || '',
        d: (m.querySelector('.d') || {}).textContent || '',
      })),
    }));""")

rep("""  check('T2 指标为现算（16 款 / 6 分类 / 5 篇 / 9 栏目页）',
    /\\b16\\b/.test(ov.view) && ov.view.includes('6 个分类') && ov.view.includes('9'), ov.view.slice(0, 300));""",
    """  const _m = {};
  (ov.metrics || []).forEach(x => { _m[x.k.trim()] = x; });
  const _pm = _m['产品'] || {}, _nm = _m['文章'] || {}, _gm = _m['栏目页 / 首页区块'] || {};
  check('T2 指标为现算（' + EXPECT.products + ' 款 / ' + EXPECT.categories + ' 分类 / '
      + EXPECT.notes + ' 篇 / ' + EXPECT.pages + ' 栏目页）',
    _pm.v.trim() === String(EXPECT.products)
      && _pm.d.trim() === String(EXPECT.categories) + ' 个分类'
      && _nm.v.trim() === String(EXPECT.notes)
      && _gm.v.trim() === String(EXPECT.pages),
    JSON.stringify(ov.metrics));""")

io.open(F, 'w', encoding='utf-8').write(s)
print('✓ T2 改为按 DOM 结构 + 真源比数')
