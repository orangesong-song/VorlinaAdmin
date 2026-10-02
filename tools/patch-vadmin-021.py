#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vorlina-admin · vadmin-021「修编辑弹窗缩略图全部图库未匹配」
2026-10-02 · 宋宋截图反馈：产品编辑弹窗里所有图片槽位显示「图库未匹配」。

真根因（代码级实锤）：
  openEd() 里 ED.doc = 整份 data/products.json 根文档（{products:[...], categories:[...]}），
  而 edImgMap() 读的是 ED.doc.sku —— 根文档上没有 sku（sku 在 products[i].sku），
  恒为 undefined ⇒ 映射表永远为空 ⇒ edThumbUrl() 永远返回 '' ⇒
  编辑弹窗所有缩略图（主图条 + 画廊）全部落到「图库未匹配」占位。

为什么拖到现在才暴露：
  ① vadmin-009/010 起 bug 就在，但 E2E 从未断言缩略图的 src，只数 .ed-thumb 个数
     （匹配失败时占位 div 也算一个，照样绿）；
  ② 产品**列表**卡片走 prodImgMap(p.sku)（传的是单个产品），一直是好的 ——
     只有编辑弹窗坏，日常改文案遇不到。

修法：
  edImgMap 改为取当前编辑节点 edGet(ED.doc, ED.sub).sku；
  非产品/分类编辑（sub 为空）时照旧返回空映射。
  verify-product-editor 补 T14b/c/d 三条断言：img src 必须命中 imagery url、
  无「图库未匹配」占位、src 走官网域 /assets/img/ 路径。

附带发现（不属本补丁）：
  .local-drafts/data/products.json 是 2026-09-23 的旧草稿，VOR-WZ-PEN 还引用
  已不存在的「针头-硅晶.jpg」⇒ 本地桩优先读 overlay ⇒ verify-product-editor T2
  在本地恒红（15/16）。生产读 GitHub 分支，不受影响。清掉旧草稿即恢复绿。
"""
import io
import sys

def patch(path, pairs):
    s = io.open(path, encoding='utf-8').read()
    for old, new in pairs:
        if new in s:
            print('跳过（已是新版）:', path)
            continue
        c = s.count(old)
        assert c == 1, '断言失败：期望 1 处、实际 %d 处 ->\n%r' % (c, old[:120])
        s = s.replace(old, new)
    io.open(path, 'w', encoding='utf-8').write(s)
    print('OK ·', path)

OLD_MAP = """function edImgMap(){
  const out = {};
  const img = STORE.files['build/data/imagery.json'];
  const sku = ED && ED.doc ? ED.doc.sku : null;
  if (img && sku && img[sku] && img[sku].items) for (const it of img[sku].items) out[it.src] = it.url;
  return out;
}"""
NEW_MAP = """function edImgMap(){
  const out = {};
  const img = STORE.files['build/data/imagery.json'];
  /* vadmin-021 修复：ED.doc 是整份 products.json 根文档，sku 在 products[i] 上 ——
     旧代码读 ED.doc.sku 恒为 undefined ⇒ 映射永远为空 ⇒ 编辑弹窗所有缩略图「图库未匹配」。
     改为取当前编辑节点（edGet(ED.doc, ED.sub)）的 sku；非产品编辑（如分类）无 sku 则照旧返回空。 */
  const node = (ED && ED.doc && ED.sub && ED.sub.length) ? edGet(ED.doc, ED.sub) : null;
  const sku = (node && typeof node === 'object') ? node.sku : null;
  if (img && sku && img[sku] && img[sku].items) for (const it of img[sku].items) out[it.src] = it.url;
  return out;
}"""

OLD_VER = '<span class="mono" style="font-size:10px;color:var(--muted)">vadmin-020</span>'
NEW_VER = '<span class="mono" style="font-size:10px;color:var(--muted)">vadmin-021</span>'

OLD_T14 = """  check('T14 缩略图条渲染（图库按 sku 匹配）', ed.thumbs === EXPECT.usableN, '实际 ' + ed.thumbs);
"""
NEW_T14 = OLD_T14 + """
  /* ── vadmin-021 回归断言：缩略图必须真的映射到 imagery url ──
     背景：edImgMap 旧代码读 ED.doc.sku（根文档没有 sku）⇒ 映射恒空 ⇒
     所有缩略图「图库未匹配」。旧断言只数 .ed-thumb 个数，匹配失败也绿 —— 漏了。 */
  section('缩略图映射 · vadmin-021');
  const th = await page.evaluate(() => ({
    imgs: [...document.querySelectorAll('#edBody .ed-thumb img')].map(i => i.getAttribute('src')).filter(Boolean),
    phN: document.querySelectorAll('#edBody .ed-thumb-ph').length,
    phText: (document.querySelector('#edBody .ed-thumb-ph') || {}).textContent || '',
  }));
  check('T14b 缩略图有真实 src（imagery 命中）', th.imgs.length === EXPECT.usableN, 'img 数 ' + th.imgs.length + ' · ' + (th.imgs[0] || '').slice(0, 90));
  check('T14c 无「图库未匹配」占位', th.phN === 0, '占位 ' + th.phN + ' · ' + th.phText.slice(0, 40));
  check('T14d 缩略图 src 走官网域 imagery 路径',
    th.imgs.length > 0 && th.imgs.every(u => u.indexOf('https://vorlina.net/assets/img/') === 0),
    (th.imgs[0] || '（无）').slice(0, 90));
"""

if __name__ == '__main__':
    patch('index.html', [(OLD_MAP, NEW_MAP), (OLD_VER, NEW_VER)])
    patch('tools/verify-product-editor.js', [(OLD_T14, NEW_T14)])
    patch('tools/verify-picker.js', [(
        "check('N1 编辑弹窗头带版本戳 vadmin-020（一眼分清旧缓存 / 新 bug）', n0.ver.indexOf('vadmin-020') >= 0, n0.ver.slice(0, 60));",
        "check('N1 编辑弹窗头带版本戳 vadmin-021（一眼分清旧缓存 / 新 bug）', n0.ver.indexOf('vadmin-021') >= 0, n0.ver.slice(0, 60));",
    )])
    print('vadmin-021 完成。回归：python3 tools/serve-local.py 8778 + node tools/verify-product-editor.js + node tools/verify-picker.js')
