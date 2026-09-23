#!/usr/bin/env python3
"""vadmin-009：产品编辑器开放图片编辑（主图 / 画廊），带 imagery 图库缩略图预览。
products.json.images.hero + images.usable 可改；lowRes / exclude（系统筛选）继续隐藏。
"""
import io, os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'index.html')
s = io.open(P, encoding='utf-8').read()

def rep(old, new, tag, n=1):
    global s
    c = s.count(old)
    assert c == n, '[%s] 断言失败：出现 %d 次（期望 %d）' % (tag, c, n)
    s = s.replace(old, new)
    print('OK [%s]' % tag)

# ── 1. 产品 schema：images 移出 hide，加 sub 白名单 + 图预览开关
rep("""    ro: { sku: '型号', category: '所属分类' },
    hide: ['nameEnStatus','categoryNote','note','status','certificationGroup','contraindication','copyRules','images'],
    hideLabel: '英文备注 / 图片清单 / 合规规则等'
  },""",
"""    ro: { sku: '型号', category: '所属分类' },
    hide: ['nameEnStatus','categoryNote','note','status','certificationGroup','contraindication','copyRules'],
    hideLabel: '英文备注 / 合规规则等',
    hasImagePreview: true,
    sub: {
      images: {
        fields: { hero: '主图（文件名，须与 imagery 图库一致）', usable: '画廊可用图（文件名列表，可增删 / 调序）' },
        hide: ['lowRes','exclude'],
        hideLabel: '低清变体 / 剔除清单（系统筛选用）'
      }
    }
  }""", '产品 schema 开放 images')

# ── 2. 图库缩略图辅助函数（插在 edKeyTag 定义之后）
rep("""const edKeyTag = (label, key) => (key && key !== label) ? ' <span class="mono dim">' + esc(key) + '</span>' : '';""",
"""const edKeyTag = (label, key) => (key && key !== label) ? ' <span class="mono dim">' + esc(key) + '</span>' : '';
const IMG_BASE = 'https://vorlina.net';
function edImgMap(){
  const out = {};
  const img = STORE.files['build/data/imagery.json'];
  const sku = ED && ED.doc ? ED.doc.sku : null;
  if (img && sku && img[sku] && img[sku].items) for (const it of img[sku].items) out[it.src] = it.url;
  return out;
}
function edThumb(fn, map, hero){
  const u = map[fn];
  if (!u) return '<div class="ed-thumb' + (hero ? ' hero' : '') + '"><span class="mono dim">' + esc(fn) + '<br>（图库未匹配）</span></div>';
  return '<div class="ed-thumb' + (hero ? ' hero' : '') + '"><img src="' + escAttr(IMG_BASE + u) + '" loading="lazy" onerror="this.style.display=\\'none\\'"><span class="mono">' + esc(fn) + '</span></div>';
}
function edImagePreviewsHTML(imagesObj){
  const map = edImgMap();
  const hero = imagesObj && imagesObj.hero ? edThumb(imagesObj.hero, map, true) : '';
  const usables = (imagesObj && imagesObj.usable ? imagesObj.usable : []).map(fn => edThumb(fn, map, false)).join('');
  return '<div class="ed-imgs"><div class="ed-imgs-h">当前图（缩略图取自 imagery 图库 · 改文件名须与图库一致）</div>'
    + '<div class="ed-thumb-row">' + hero + usables + '</div></div>';
}""", '图库缩略图辅助')

# ── 3. edNodeHTML 对象分支：① 子对象传 sub schema ② 产品级附图预览
rep("""      return edNodeHTML(path.concat(k), v[k], F[k] || k, null, k);
    }).join('')
      + (hiddenN ? '<div class="ed-ro">🔒 已隐藏 ' + hiddenN + ' 个内部字段' + (S.hideLabel ? '（' + esc(S.hideLabel) + '）' : '') + '—— 系统识别用，不在页面编辑。</div>' : '');
    return '<div class="ed-obj"><div class="ed-obj-h">' + esc(keyLabel) + edKeyTag(keyLabel, origKey) + '</div>' + kids + '</div>';
  }""",
"""      return edNodeHTML(path.concat(k), v[k], F[k] || k, (S.sub && S.sub[k]) ? S.sub[k] : null, k);
    }).join('')
      + (S.hasImagePreview && v.images ? edImagePreviewsHTML(v.images) : '')
      + (hiddenN ? '<div class="ed-ro">🔒 已隐藏 ' + hiddenN + ' 个内部字段' + (S.hideLabel ? '（' + esc(S.hideLabel) + '）' : '') + '—— 系统识别用，不在页面编辑。</div>' : '');
    return '<div class="ed-obj"><div class="ed-obj-h">' + esc(keyLabel) + edKeyTag(keyLabel, origKey) + '</div>' + kids + '</div>';
  }""", '对象分支传 sub + 图预览')

# ── 4. images 子对象表头提示（图库为准）
rep("""  .ed-ro{font-family:var(--mono);font-size:11px;color:var(--muted);margin:6px 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}""",
"""  .ed-ro{font-family:var(--mono);font-size:11px;color:var(--muted);margin:6px 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .ed-imgs{margin:10px 0 4px;padding:10px;border:1px dashed var(--line);background:rgba(0,0,0,.02)}
  .ed-imgs-h{font-size:12px;color:var(--muted);margin-bottom:8px}
  .ed-thumb-row{display:flex;flex-wrap:wrap;gap:8px}
  .ed-thumb{width:84px;border:1px solid var(--line);border-radius:3px;overflow:hidden;background:#fff;font-size:9px;text-align:center}
  .ed-thumb.hero{outline:2px solid var(--gold);outline-offset:-1px}
  .ed-thumb img{width:84px;height:64px;object-fit:cover;display:block;background:#eee}
  .ed-thumb span{display:block;padding:3px 2px;word-break:break-all;color:var(--muted)}""", '图预览 CSS')

io.open(P, 'w', encoding='utf-8').write(s)
print('补丁完成')
