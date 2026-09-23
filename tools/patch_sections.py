#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vadmin-011 · 分区表单推广到「栏目页 / 首页 / 文章 / 分类」
只改 index.html（内联 style + 内联 script）。每处替换都带出现次数断言 —— NAS 上 Edit 会误报 modified，
所以用 python 补丁脚本 + 断言，改不到就报错而不是静默漏改。
"""
import io, os, sys

F = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'index.html')
F = os.path.abspath(F)
s = io.open(F, encoding='utf-8').read()
orig_len = len(s)

def rep(old, new, n=1, tag=''):
    global s
    c = s.count(old)
    assert c == n, '[%s] 期望出现 %d 次，实际 %d 次' % (tag or old[:40], n, c)
    s = s.replace(old, new, n)
    print('  ok  %-34s (%d 处)' % (tag or old[:34].replace('\n', ' '), c))

print('>>> 1) CSS：分区折叠')
rep(
"  .edsec-note{font-size:12px;color:var(--muted);margin:0 0 9px}",
"""  .edsec-note{font-size:12px;color:var(--muted);margin:0 0 9px}
  .edsec-h{display:flex;align-items:center;gap:8px;cursor:pointer;user-select:none}
  .edsec-h .sec-tog{margin-left:auto;font-size:10px;color:var(--muted);letter-spacing:.08em}
  .edsec.folded .edsec-b{display:none}
  .ccard{border:1px solid var(--line);background:#fff;display:flex;flex-direction:column}
  .ccard-thumb{height:104px;background:#F5F3EF;display:flex;align-items:center;justify-content:center;overflow:hidden;border-bottom:1px solid var(--line)}
  .ccard-thumb img{max-width:100%;max-height:100%;object-fit:contain;display:block}
  .ccard-b{padding:10px 12px;flex:1}
  .ccard-k{font-family:var(--mono);font-size:11px;letter-spacing:.1em;color:var(--muted)}
  .ccard-name{font-size:14px;line-height:1.45;margin:4px 0 5px;color:var(--ink)}
  .ccard-meta{font-size:12px;color:var(--muted)}
  .ccard-f{display:flex;align-items:center;gap:8px;padding:8px 12px;border-top:1px solid var(--line)}
  .ccard-f .grow{margin-left:auto}""",
tag='CSS 追加')

print('>>> 2) 中文标签字典 ED_LABELS + 分区说明 ED_SEC_NOTE')
LABELS = """/* ── 中文标签字典（vadmin-011）────────────────────────────────
   运营看到的每一格都要是中文。键名 → 中文；schema.fields 的标签优先级更高。
   这份字典按真源里实际出现的键名整理（python walk 全量 JSON 得来），不猜。 */
const ED_LABELS = {
  /* 通用 / SEO */
  meta:'SEO 与分享卡片', title:'标题', description:'页面描述', ogTitle:'分享标题', ogDescription:'分享描述',
  ogType:'分享类型', path:'页面路径', crumb:'面包屑', kind:'类型', status:'状态',
  pageHead:'页头', num:'栏号', h1:'主标题', h2:'小标题', h3:'三级标题', lede:'导语', side:'侧边说明',
  items:'条目', rows:'表格行', steps:'步骤', bullets:'要点', cards:'卡片', paragraphs:'段落', buttons:'按钮组',
  text:'正文', t:'块类型', v:'内容', k:'项目', b:'加粗小标题', p:'段落正文', n:'序号', d:'说明', nm:'名称',
  table:'表格', caption:'表格标题', label:'按钮文字', href:'链接地址', img:'图片文件名',
  width:'宽', height:'高', w:'宽', h:'高', alt:'图片说明（无障碍读屏）', src:'图片文件名', file:'文件名',
  source:'来源', note:'说明', detail:'详情', tone:'语气 / 版式标记', appliesTo:'适用范围', models_note:'型号说明',
  /* 产品 / 分类 */
  categories:'分类区', category:'所属分类', slug:'链接标识', short:'短名', en:'英文名', zh:'中文名',
  eyebrow:'眉标', cardNote:'卡片说明', cardImage:'卡片图（文件名）', cardAlt:'卡片图说明',
  nameZh:'中文名', nameEn:'英文名', tagline:'一句话卖点', deviceType:'产品形态', moq:'最小起订量',
  leadTime:'交期（工作日）', warranty:'质保', packages:'包装', specs:'规格参数', images:'图片',
  hero:'主图', usable:'画廊可用图', ix:'编号', card:'列表卡片摘要', cardW:'卡片图宽', cardH:'卡片图高',
  readMins:'预计阅读（分钟）', date:'发布日期', blocks:'正文块', hub:'列表页头', catalogue:'目录卡', notes:'文章列表',
  /* 首页区块 */
  heroSec:'首屏', categoriesCardsFromPage:'分类卡（取自栏目页）', mosaic:'产品马赛克', about:'关于我们',
  why:'为什么选我们', certwall:'证书墙', gallery:'展厅', expo:'展会', facebook:'Facebook 动态',
  reviews:'客户评价', insights:'文章区', oem:'定制 OEM', faq:'常见问题', cta:'结尾召唤',
  tiles:'瓦片图', logo:'Logo', logoAlt:'Logo 说明', range:'产品线说明', tag:'标签', stats:'数据条',
  count:'数值', display:'显示值', sep:'分隔符', mid:'中间文本', unit:'单位', after:'后缀',
  imgs:'图片组', icon:'图标', certs:'证书清单', ledePre:'导语前段', ledeLink:'导语链接文字',
  ledePost:'导语后段', linkText:'链接文字', published:'发布时间', ap:'适用认证', dlmeta:'下载信息',
  wide:'宽版', btn:'按钮', posts:'文章条目', hint:'提示', footnote:'脚注', dataCap:'数据口径说明', cap:'说明',
  /* 栏目页区块 */
  buyerProfiles:'买家画像', sameTerms:'行业叫法', regulatory:'合规说明', whatCanBeChanged:'可定制项',
  howOemRuns:'定制流程', whatToSend:'需你提供的资料', timeline:'时间表', atAGlance:'工厂一览',
  onSite:'工厂现场', quality:'质检流程', development:'研发', documents:'证书文件', documentsSection:'证书区',
  directiveSection:'法规区', howToRead:'怎么读证书', whatWeSend:'我们会提供', arrival:'到货与验收',
  training:'培训', consumables:'耗材', beforeYouWrite:'写信前请读', disclaimer:'免责声明', form:'表单文案',
  enquirySection:'询盘区说明', channels:'联系方式', whatToInclude:'请附上这些信息', visiting:'来访',
  band:'通栏', cols:'站点地图列', oemSteps:'定制步骤', proNotice:'专业买家提示', shots:'现场照片',
  name:'姓名', company:'公司', email:'邮箱', country:'国家', phone:'电话', message:'留言'
};
/* 分区脚注：告诉运营这一格改了会影响什么 */
const ED_SEC_NOTE = {
  meta:'只影响搜索结果与分享卡片 —— 不显示在页面正文里。',
  pvbar:'内部预览条，页面上线后不展示。',
  pageHead:'页面顶部的大标题与导语。',
  crumb:'面包屑（页面顶部的小路径）。',
  cardImage:'首页分类卡上的图。文件名必须与仓库 assets/img/ 下的图一致。',
  blocks:'正文按块排：h2 小标题 / p 段落 / ul 列表 / table 表格 / notice 提示。块可增删、可调序。',
  bullets:'分类页顶部列出的卖点，一行一条。'
};
"""
rep("const ED_SCHEMA = {", LABELS + "const ED_SCHEMA = {", tag='插入字典')

print('>>> 3) schema 补「分类」「文章页头 / 目录卡」')
rep("""    sub: {
      images: {
        fields: { hero: '主图（文件名，须与 imagery 图库一致）', usable: '画廊可用图（文件名列表，可增删 / 调序）' },
        hide: ['lowRes','exclude'],
        hideLabel: '低清变体 / 剔除清单（系统筛选用）'
      }
    }""",
"""    sub: {
      images: {
        fields: { hero: '主图（文件名，须与 imagery 图库一致）', usable: '画廊可用图（文件名列表，可增删 / 调序）' },
        hide: ['lowRes','exclude'],
        hideLabel: '低清变体 / 剔除清单（系统筛选用）'
      },
      categories: {
        fields: { short:'短名（卡片上显示）', zh:'中文名', en:'英文名', eyebrow:'眉标（小字标签）',
                  cardImage:'卡片图文件名', cardAlt:'卡片图说明', cardNote:'卡片一句话', lede:'分类页导语',
                  bullets:'卖点要点（一行一条）' },
        ro: { slug: '链接标识 slug' },
        hideLabel: '（分类无内部字段）'
      }
    }""",
tag='products.sub.categories')

rep("""    ro: { slug: 'slug（链接标识）', ix: '编号', status: '发布状态' },
    hide: ['image','cardW','cardH'],
    hideLabel: '配图文件名 / 尺寸标记'
  },""",
"""    ro: { slug: 'slug（链接标识）', ix: '编号', status: '发布状态' },
    hide: ['image','cardW','cardH'],
    hideLabel: '配图文件名 / 尺寸标记',
    sub: {
      hub: { fields: { num:'栏号', h1:'主标题', lede:'导语', side:'侧边说明', crumb:'面包屑', path:'页面路径' } },
      catalogue: { fields: { num:'栏号', h3:'小标题', p:'说明文字', meta:'补充说明', file:'PDF 文件名', more:'更多链接文字' } }
    }
  },""",
tag='insights.sub')

print('>>> 4) edSchemaFor 支持 sub[0] 级 schema（分类 / hub / 目录卡）')
rep("""  if (s.itemOf) return (sub && sub[0] === s.itemOf) ? s : null;
  return (sub && sub.length) ? null : s;""",
"""  if (s.itemOf){
    if (sub && sub[0] === s.itemOf) return s;
    /* 同一个文件里的其它条目（分类 / 文章页头 / 目录卡）走各自的 sub schema */
    return (sub && sub.length && s.sub && s.sub[sub[0]]) ? s.sub[sub[0]] : null;
  }
  return (sub && sub.length) ? null : s;""",
tag='edSchemaFor')

print('>>> 5) edSec 加折叠 + 只读行 helper')
rep("""function edSec(title, note, body){
  return '<div class="edsec"><div class="edsec-h">' + esc(title) + '</div><div class="edsec-b">'
    + (note ? '<div class="edsec-note">' + note + '</div>' : '') + body + '</div></div>';
}""",
"""function edSec(title, note, body){
  return '<div class="edsec"><div class="edsec-h" data-sec title="点击收起 / 展开">'
    + '<span>' + esc(title) + '</span><span class="sec-tog">− 收起</span></div><div class="edsec-b">'
    + (note ? '<div class="edsec-note">' + note + '</div>' : '') + body + '</div></div>';
}
function edRoRow(label, val){
  return '<div class="ed-ro" title="结构键：改动会牵动页面链接与归组，只读">' + esc(label)
    + ' · <span class="mono">' + esc(String(val == null ? '' : val).slice(0, 60)) + '</span> · 只读</div>';
}
function edThumbDirect(url, fn, hero){
  return '<div class="ed-thumb' + (hero ? ' hero' : '') + '">'
    + '<img src="' + escAttr(url) + '" loading="lazy" onerror="this.style.display=\\'none\\'">'
    + '<span class="mono">' + esc(fn) + '</span></div>';
}""",
tag='edSec 折叠')

print('>>> 6) 新增：分区渲染 / 分类表单 / 文章表单 / 分派')
NEW_FUNCS = r"""/* ── 通用分区渲染（vadmin-011）─────────────────────────────
   asSec=true：每个键一个分区卡片（整页编辑时用，如栏目页 meta / pageHead / 各区块）；
   asSec=false：键平铺在一个分区里（编辑首页某个区块时用，免得 12 个字段切成 12 个分区）。
   隐藏与只读沿用 vadmin-008 的白名单判据；增 / 删 / 调序仍走通用 edNodeHTML，一份逻辑不写第二套。 */
function edSectionsHTML(path, obj, sch, asSec){
  const S = sch || {};
  const hide = S.hide || [], deny = S.deny || [], F = S.fields || {}, R = S.ro || {};
  let hiddenN = 0, roRows = '', secs = '';
  for (const k of Object.keys(obj)){
    if (hide.indexOf(k) >= 0 || deny.indexOf(k) >= 0 || k.charAt(0) === '_'){ hiddenN++; continue }
    if (R[k]){ roRows += edRoRow(F[k] || R[k], obj[k]); continue }
    const lab = F[k] || ED_LABELS[k] || k;
    const subSch = (S.sub && S.sub[k]) ? S.sub[k] : null;
    const inner = edNodeHTML(path.concat(k), obj[k], lab, subSch, k);
    secs += asSec ? edSec(lab, ED_SEC_NOTE[k] || '', inner) : inner;
  }
  let out = '';
  if (roRows) out += edSec('只读 · 结构键', '这些键牵动页面链接与归组，需要改请找管理员。', roRows);
  out += secs;
  if (hiddenN) out += '<div class="ed-ro">🔒 已隐藏 ' + hiddenN + ' 个内部字段'
    + (S.hideLabel ? '（' + esc(S.hideLabel) + '）' : '') + ' —— 系统识别用，不在页面编辑。</div>';
  return out || '<div class="ed-ro">（这份内容里没有可编辑字段）</div>';
}
function edGenericHTML(){
  const v = edGet(ED.doc, ED.sub);
  const sch = edSchemaFor(ED.path, ED.sub);
  if (v && typeof v === 'object' && !Array.isArray(v)){
    if (!ED.sub.length) return edSectionsHTML(ED.sub, v, sch, true);      /* 整页：顶层键各占一区 */
    const topKey = ED.sub[ED.sub.length - 1];
    const lab = (sch && sch.fields && sch.fields[topKey]) || ED_LABELS[topKey] || topKey;
    return edSec(lab, ED_SEC_NOTE[topKey] || '', edSectionsHTML(ED.sub, v, sch, false));
  }
  return edSectionsHTML(ED.sub, v, sch, false);
}
/* 分类分区表单：① 首页分类卡 ② 分类名与导语 ③ 卖点要点 ④ 只读 slug */
function edCategoryHTML(){
  const S = (ED_SCHEMA['data/products.json'].sub || {}).categories || {};
  const base = ED.sub, c = edGet(ED.doc, base) || {};
  const L = k => (S.fields && S.fields[k]) || ED_LABELS[k] || k;
  const url = c.cardImage ? IMG_BASE + '/assets/img/' + c.cardImage : '';
  const card = ['short','cardImage','cardAlt','eyebrow','cardNote']
    .map(k => edFieldRow(base.concat(k), L(k), k, c[k])).join('')
    + (url
        ? '<div class="ed-imgs"><div class="ed-imgs-h">卡片图预览（仓库 assets/img/ 下的同名文件）</div>'
          + '<div class="ed-thumb-row">' + edThumbDirect(url, c.cardImage, true) + '</div></div>'
        : '<div class="edsec-note">卡片图未填 —— 填了文件名且仓库里有同名图时这里会出现预览。</div>');
  const names = ['zh','en'].map(k => edFieldRow(base.concat(k), L(k), k, c[k])).join('')
    + '<label class="ed-field"><span class="ed-k">' + esc(L('lede')) + edKeyTag(L('lede'), 'lede') + '</span>'
    + edArea(base.concat('lede'), c.lede, 4) + '</label>';
  return edSec('① 首页分类卡', '出现在首页分类区与 /products/ 总览页的卡片上 —— 一份数据两处渲染。', card)
    + edSec('② 分类名与导语', '', names)
    + edSec('③ 卖点要点', '分类页顶部逐条列出，可增删 / 调序。',
            edNodeHTML(base.concat('bullets'), c.bullets || [], '要点（一行一条）', null, 'bullets'))
    + edSec('④ 只读 · 结构键', '改 slug 会牵动分类页链接，需要改请找管理员。', edRoRow('链接标识 slug', c.slug));
}
/* 文章分区表单：① 基本信息 ② 只读（slug / 编号 / 状态）③ 配图 ④ 正文块 */
function edNoteHTML(){
  const S = ED_SCHEMA['build/data/insights.json'];
  const base = ED.sub, n = edGet(ED.doc, base) || {};
  const L = k => (S.fields && S.fields[k]) || ED_LABELS[k] || k;
  const basics = ['title','card','cardAlt'].map(k => edFieldRow(base.concat(k), L(k), k, n[k])).join('')
    + '<label class="ed-field"><span class="ed-k">' + esc(L('lede')) + edKeyTag(L('lede'), 'lede') + '</span>'
    + edArea(base.concat('lede'), n.lede, 4) + '</label>'
    + '<label class="ed-field"><span class="ed-k">' + esc(L('alt')) + edKeyTag(L('alt'), 'alt') + '</span>'
    + edArea(base.concat('alt'), n.alt, 2) + '</label>'
    + ['date','readMins'].map(k => edFieldRow(base.concat(k), L(k), k, n[k])).join('');
  const ro = ['slug','ix','status'].map(k =>
    edRoRow((S.ro && S.ro[k]) || ED_LABELS[k] || k, n[k])).join('');
  const img = n.image ? IMG_BASE + n.image : '';
  const imgBody = '<div class="edsec-note">正文配图按路径引用仓库图片；改了文件名必须仓库里也有同名图，否则线上会裂图。</div>'
    + (img ? '<div class="ed-thumb-row">' + edThumbDirect(img, n.image, true) + '</div>' : '')
    + '<label class="ed-field"><span class="ed-k">' + esc(L('image') || '配图路径') + edKeyTag('配图路径', 'image') + '</span>'
    + '<input class="ed-in" data-ed="' + escAttr(JSON.stringify(base.concat('image'))) + '" value="'
    + escAttr(String(n.image == null ? '' : n.image)) + '"></label>';
  return edSec('① 基本信息', '', basics)
    + edSec('② 只读 · 链接与状态', 'slug 决定文章链接；status 为 published 才出现在列表页。', ro)
    + edSec('③ 配图', '', imgBody)
    + edSec('④ 正文块', ED_SEC_NOTE.blocks || '',
            edNodeHTML(base.concat('blocks'), n.blocks || [], '正文块', null, 'blocks'));
}
function edKind(){
  if (!ED) return '';
  if (ED.path === 'data/products.json'){
    if (ED.sub[0] === 'products') return 'product';
    if (ED.sub[0] === 'categories') return 'category';
  }
  if (ED.path === 'build/data/insights.json' && ED.sub[0] === 'notes') return 'note';
  return 'generic';
}
"""
rep("function edNodeHTML(path, v, keyLabel, sch, origKey){", NEW_FUNCS + "function edNodeHTML(path, v, keyLabel, sch, origKey){", tag='插入新函数')

print('>>> 7) edNodeHTML：子键标签查字典')
rep("      return edNodeHTML(path.concat(k), v[k], F[k] || k, (S.sub && S.sub[k]) ? S.sub[k] : null, k);",
    "      return edNodeHTML(path.concat(k), v[k], F[k] || ED_LABELS[k] || k, (S.sub && S.sub[k]) ? S.sub[k] : null, k);",
    tag='edNodeHTML 标签')

print('>>> 8) edRender 按内容类型分派')
rep("""  const isProd = (ED.path === 'data/products.json' && ED.sub[0] === 'products');
  document.getElementById('edBody').innerHTML = isProd
    ? edProductHTML()
    : edNodeHTML(ED.sub, edGet(ED.doc, ED.sub), ED.sub.length ? String(ED.sub[ED.sub.length - 1]) : ED.path, edSchemaFor(ED.path, ED.sub));""",
"""  const k = edKind();
  document.getElementById('edBody').innerHTML =
      k === 'product'  ? edProductHTML()
    : k === 'category' ? edCategoryHTML()
    : k === 'note'     ? edNoteHTML()
    :                    edGenericHTML();""",
tag='edRender 分派')

print('>>> 9) 点击分区标题折叠')
rep("""document.addEventListener('click', e => {
  const opener = e.target.closest('[data-opened]');""",
"""document.addEventListener('click', e => {
  const secH = e.target.closest('[data-sec]');
  if (secH){
    const box = secH.parentElement; if (!box) return;
    const folded = box.classList.toggle('folded');
    const tog = secH.querySelector('.sec-tog');
    if (tog) tog.textContent = folded ? '＋展开' : '− 收起';
    return;
  }
  const opener = e.target.closest('[data-opened]');""",
tag='折叠事件')

print('>>> 10) 分类列表改卡片（缩略图 + 在架款数）')
rep("""    const catRows = cats.map((c, ci) => row(
      [esc(c.slug), esc(c.en || '-'), esc(c.short || '-'), String(cnt[c.slug] || 0), String(((c.bullets) || []).length),
       pr ? edBtn('data/products.json', ['categories', ci], '分类 · ' + c.slug) : '-'],
      { kAt:[0], numAt:[3,4] })).join('');""",
"""    const catCards = cats.map((c, ci) => {
      const u = c.cardImage ? IMG_BASE + '/assets/img/' + c.cardImage : '';
      return '<div class="ccard">'
        + '<div class="ccard-thumb">' + (u
            ? '<img src="' + escAttr(u) + '" loading="lazy" alt="" onerror="this.style.display=\\'none\\'">'
            : '<span class="mono dim" style="font-size:11px">无图</span>') + '</div>'
        + '<div class="ccard-b">'
        +   '<div class="ccard-k">' + esc(c.slug) + '</div>'
        +   '<div class="ccard-name">' + esc(c.zh || c.short || '-') + '</div>'
        +   '<div class="ccard-meta">' + esc(c.short || '-') + ' · 在架 ' + (cnt[c.slug] || 0) + ' 款</div>'
        + '</div>'
        + '<div class="ccard-f"><span class="mono dim" style="font-size:11px">' + ((c.bullets || []).length) + ' 条要点</span>'
        +   '<span class="grow"></span>'
        +   (pr ? edBtn('data/products.json', ['categories', ci], '分类 · ' + c.slug) : '-')
        + '</div></div>';
    }).join('');""",
tag='分类卡片')

rep("""    <div class="panel sec">
      <div class="panel-h"><span class="ttl">分类 · ${cats.length}</span></div>
      <table class="tbl">${head(['SLUG','分类名','短名','在架款数','要点数','编辑'],[3,4])}
        <tbody>${catRows || '<tr><td colspan="6" class="empty">读不到分类数据</td></tr>'}</tbody>
      </table>
    </div>""",
"""    <div class="panel sec">
      <div class="panel-h"><span class="ttl">分类 · ${cats.length}</span><span class="grow"></span>
        <span class="mono dim" style="font-size:11px">点卡片右下角「改」进分区表单</span></div>
      <div class="pgrid">${catCards || '<div class="pcard-empty">读不到分类数据</div>'}</div>
    </div>""",
tag='分类面板')

print('>>> 11) 三处引导文案同步（别让页面说谎）')
rep("""      点卡片右下角「改」进入<strong>分区表单</strong>：① 基础信息 ② 型号与分类（只读）③ 包装 ④ 规格参数 ⑤ 图片。
      运营只填格子；内部字段（英文备注 / 合规规则等）<strong>已整体隐藏</strong>，不会被误改；sku / category 等结构键只读。
      保存进的是草稿，「变更清单」过目后发布才上线。""",
"""      点卡片右下角「改」进入<strong>分区表单</strong>：型号是 ① 基础信息 ② 型号与分类（只读）③ 包装 ④ 规格参数 ⑤ 图片；
      分类是 ① 首页分类卡 ② 分类名与导语 ③ 卖点要点 ④ 只读 slug。
      运营只填格子；内部字段（英文备注 / 合规规则等）<strong>已整体隐藏</strong>，不会被误改；sku / category / slug 等结构键只读。
      分区标题可点击收起；保存进的是草稿，「变更清单」过目后发布才上线。""",
tag='产品页引导')

rep("""      <b>块编辑已开放</b>
      点行尾「改」：标题 / 日期 / 状态 / 摘要直接改；正文是 blocks[]（h2 / p / ul / ol / table / notice），
      每块一项，可改可增可删可调序。发布后列表页、详情页与 JSON-LD 同步更新 —— 一份数据两处渲染。""",
"""      <b>文章也是分区表单</b>
      点行尾「改」：① 基本信息（标题 / 摘要 / 导语 / 日期 / 篇幅）② 只读的 slug 与发布状态 ③ 配图 ④ 正文块
      （h2 / p / ul / ol / table / notice，每块一项，可改可增可删可调序）。
      发布后列表页、详情页与 JSON-LD 同步更新 —— 一份数据两处渲染。""",
tag='文章页引导')

rep("""      <b>整页编辑</b>
      点行尾「改」打开该页完整文案树：meta（SEO 标题 / 描述）、各区块的字段与列表都能改。
      「区块数」是按顶层字段现算的，加删区块它会自己变。说明性字段（下划线开头）只读展示，防手滑。""",
"""      <b>整页分区编辑</b>
      点行尾「改」：一个区块一个分区卡片（SEO 与分享卡片 / 页头 / 各内容区块），分区标题可点击收起。
      meta 只影响搜索结果与分享卡片；「区块数」按顶层字段现算，加删区块它会自己变。
      说明性字段（下划线开头）整体隐藏，防手滑。""",
tag='栏目页引导')

io.open(F, 'w', encoding='utf-8').write(s)
print('\n写完：%s  %d → %d 字节（+%.1f KB）' % (os.path.basename(F), orig_len, len(s), (len(s) - orig_len) / 1024.0))
