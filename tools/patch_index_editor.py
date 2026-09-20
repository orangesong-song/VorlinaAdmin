#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""index.html 补丁：接通「编辑 → 保存草稿 → 变更清单 → 发布」全链路。
① 通用递归叶子编辑器（结构键只读展示、值可改、数组项可增删复制排序）
② products/notes/pages/home/certs 接入「改」按钮
③ changes 页真实现（POST /changes 对比 + 发布 + boss 回滚）
④ releases 页接 GET /commits
⑤ overview 发布链路面板改为已接入
全部替换带出现次数断言。"""
import io, os

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..', 'index.html')
src = io.open(P, encoding='utf-8').read()
orig = src

def rep(old, new, tag, n=1):
    global src
    c = src.count(old)
    assert c == n, '断言失败 [%s]：%r 出现 %d 次（期望 %d）' % (tag, old[:70], c, n)
    src = src.replace(old, new)
    print('OK [%s]' % tag)

# ═══ 1. CSS ═══════════════════════════════════════════════════════
rep('  .pair .v{font-size:13.5px;color:var(--ink)}\n</style>',
'''  .pair .v{font-size:13.5px;color:var(--ink)}

  /* ── 通用编辑器 ─────────────────────────────────────────── */
  .ed-mask{position:fixed;inset:0;background:rgba(21,22,26,.45);z-index:60}
  .ed-panel{position:fixed;top:20px;bottom:20px;left:50%;transform:translateX(-50%);width:min(880px,94vw);
    background:var(--paper);border:1px solid var(--ink);z-index:61;display:flex;flex-direction:column}
  .ed-head{display:flex;align-items:center;gap:12px;padding:13px 20px;border-bottom:1px solid var(--line)}
  .ed-head .t{font-family:var(--serif);font-size:18px;font-weight:600;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .ed-body{overflow:auto;padding:16px 20px;flex:1}
  .ed-obj{border:1px solid var(--line);padding:8px 14px 10px;margin:8px 0}
  .ed-obj-h,.ed-arr-h,.ed-item-h{font-family:var(--mono);font-size:11px;letter-spacing:.12em;color:var(--muted);text-transform:uppercase;margin:8px 0 2px}
  .ed-item{border:1px solid var(--line);padding:6px 12px 8px;margin:8px 0;background:var(--card)}
  .ed-ops{float:right;display:flex;gap:6px}
  .ed-ops .btn{font-size:11px;padding:2px 8px}
  .ed-ops .btn.risk{color:var(--warn)}
  .ed-field{display:block;margin:10px 0}
  .ed-k{display:block;font-family:var(--mono);font-size:11px;letter-spacing:.1em;color:var(--muted);margin-bottom:4px;text-transform:uppercase}
  .ed-in{width:100%;box-sizing:border-box;font:inherit;font-size:13px;padding:7px 9px;border:1px solid var(--line);background:#fff;color:var(--ink)}
  .ed-in:focus{outline:none;border-color:var(--gold)}
  textarea.ed-in{resize:vertical;line-height:1.65}
  .ed-ro{font-family:var(--mono);font-size:11px;color:var(--muted);margin:6px 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .ed-msg{padding:10px 20px;border-top:1px solid var(--line);min-height:40px;font-size:13px}
</style>''', 'css')

# ═══ 2. STORE 字段 ════════════════════════════════════════════════
rep("const STORE = { files:{}, errors:[], version:'-', inquiries:null, inquiriesError:'', loadedAt:0 };",
    "const STORE = { files:{}, errors:[], version:'-', inquiries:null, inquiriesError:'', loadedAt:0,\n"
    "  changes:null, changesError:'', changesLoading:false,\n"
    "  commits:null, commitsError:'', commitsLoading:false, publishMsg:'' };", 'store')

# ═══ 3. escAttr + edBtn（贴在 esc 后面）════════════════════════════
rep("""function esc(s){
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}""",
"""function esc(s){
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function escAttr(s){
  return esc(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
/* 「改」按钮：data-opened 存 [path, sub, label]，统一由全局委托打开编辑器 */
const edBtn = (path, sub, label) =>
  '<button class="btn ghost sm" data-opened="' + escAttr(JSON.stringify([path, sub || [], label || path])) + '">改</button>';""", 'escattr')

# ═══ 4. 编辑器 + 变更/发布逻辑（插在启动段之前）═════════════════════
rep("""/* ── 启动：有会话就恢复（过期先续），没有就停在登录页 ── */""",
"""/* ══════════════════════════════════════════════════════════════
   通用编辑器（P1 第 3 步 · 2026-09-20）
   设计：结构键只读展示（改名会断链/串分类）、叶子值可改、数组项可增删复制排序。
   保存 = 整文件 PUT 到 cms 草稿分支 —— 绝不碰 main，更不碰页面 HTML。
   ══════════════════════════════════════════════════════════════ */
let ED = null;
const edGet = (o, path) => path.reduce((a,k) => a[k], o);
const edSet = (o, path, v) => { const ks = [...path]; const last = ks.pop(); ks.reduce((a,k) => a[k], o)[last] = v; };

function edBlank(v){
  if (typeof v === 'string') return '';
  if (typeof v === 'number') return 0;
  if (typeof v === 'boolean') return false;
  if (Array.isArray(v)) return [];
  if (v && typeof v === 'object'){
    const o = {};
    for (const k of Object.keys(v)) o[k] = (k === 't' && typeof v[k] === 'string') ? v[k] : edBlank(v[k]);
    return o;
  }
  return null;
}
function edLeafHTML(path, v){
  const p = escAttr(JSON.stringify(path));
  if (typeof v === 'string'){
    if (v.includes('\\n') || v.length > 60){
      const rows = Math.min(14, v.split('\\n').length + 2);
      return '<textarea class="ed-in" data-ed="' + p + '" rows="' + rows + '">' + esc(v) + '</textarea>';
    }
    return '<input class="ed-in" data-ed="' + p + '" value="' + escAttr(v) + '">';
  }
  if (typeof v === 'number')
    return '<input class="ed-in" data-ed="' + p + '" data-edtype="num" value="' + escAttr(String(v)) + '">';
  if (typeof v === 'boolean')
    return '<select class="ed-in" data-ed="' + p + '" data-edtype="bool">'
      + '<option value="true"' + (v ? ' selected' : '') + '>true</option>'
      + '<option value="false"' + (!v ? ' selected' : '') + '>false</option></select>';
  return '<span class="mono dim">null · 不动</span>';
}
function edNodeHTML(path, v, keyLabel){
  if (v && typeof v === 'object' && !Array.isArray(v)){
    const kids = Object.keys(v).map(k => {
      if (k.startsWith('_')) return '<div class="ed-ro" title="' + escAttr(String(v[k]).slice(0,200)) + '">' + esc(k) + ' · ' + esc(String(v[k]).slice(0,90)) + '</div>';
      return edNodeHTML(path.concat(k), v[k], k);
    }).join('');
    return '<div class="ed-obj"><div class="ed-obj-h">' + esc(keyLabel) + '</div>' + kids + '</div>';
  }
  if (Array.isArray(v)){
    const lp = escAttr(JSON.stringify(path));
    const items = v.map((it, i) => {
      const ops = '<span class="ed-ops">'
        + '<button class="btn ghost" data-edop="up" data-edlist="' + lp + '" data-edi="' + i + '" title="上移">↑</button>'
        + '<button class="btn ghost" data-edop="down" data-edlist="' + lp + '" data-edi="' + i + '" title="下移">↓</button>'
        + '<button class="btn ghost" data-edop="dup" data-edlist="' + lp + '" data-edi="' + i + '">复制</button>'
        + '<button class="btn ghost risk" data-edop="del" data-edlist="' + lp + '" data-edi="' + i + '">删</button></span>';
      return '<div class="ed-item"><div class="ed-item-h">项 ' + i + ops + '</div>'
        + edNodeHTML(path.concat(i), it, String(i)) + '</div>';
    }).join('');
    const add = '<button class="btn ghost sm" data-edop="add" data-edlist="' + lp + '">＋插入一项</button>';
    return '<div class="ed-obj"><div class="ed-arr-h">' + esc(keyLabel) + ' · ' + v.length + ' 项　' + add + '</div>'
      + (items || '<div class="ed-ro">（空列表 —— 点「插入一项」新增）</div>') + '</div>';
  }
  return '<label class="ed-field"><span class="ed-k">' + esc(keyLabel) + '</span>' + edLeafHTML(path, v) + '</label>';
}
function openEd(path, sub, label){
  if (!STORE.files[path]){ alert('这份内容还没读到，无法编辑。请先回总览确认真源读取正常。'); return }
  ED = { path, sub: sub || [], label: label || path,
         doc: JSON.parse(JSON.stringify(STORE.files[path])),
         message: '后台编辑 · ' + (label || path) };
  document.getElementById('edMsg').textContent = '';
  edRender();
}
function edRender(){
  if (!ED) return;
  document.getElementById('edTitle').textContent = ED.label + '　·　' + ED.path;
  document.getElementById('edBody').innerHTML = edNodeHTML(ED.sub, edGet(ED.doc, ED.sub), ED.sub.length ? String(ED.sub[ED.sub.length - 1]) : ED.path);
  document.getElementById('edWrap').hidden = false;
}
function closeEd(){ ED = null; document.getElementById('edWrap').hidden = true }
async function saveEd(){
  if (!ED) return;
  const btn = document.getElementById('edSave');
  const old = btn.textContent;
  btn.disabled = true; btn.textContent = '保存中…';
  document.getElementById('edMsg').textContent = '';
  try {
    await contentPut(ED.path, ED.doc, ED.message);
    STORE.files[ED.path] = JSON.parse(JSON.stringify(ED.doc));
    document.getElementById('edMsg').innerHTML = '<b style="color:var(--ok)">已保存到草稿（cms 分支）。</b>还没上线 —— 去「变更清单」过目后点发布。';
  } catch(e){
    document.getElementById('edMsg').innerHTML = '<b style="color:var(--warn)">保存失败：</b>' + esc(e.message || String(e));
  } finally { btn.disabled = false; btn.textContent = old }
}

/* ── 变更对比 / 发布历史 / 发布动作 ─────────────────────────── */
async function refreshChanges(){
  STORE.changesLoading = true; STORE.changesError = ''; STORE.changes = null; STORE.publishMsg = '';
  if (current === 'changes') go('changes');
  try {
    const j = await contentFetch(CONTENT_BASE + '/changes', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths: CONTENT_JSON })
    });
    STORE.changes = j.files || [];
  } catch(e){ STORE.changesError = e.message || String(e) }
  STORE.changesLoading = false;
  if (current === 'changes') go('changes');
}
async function refreshCommits(){
  STORE.commitsLoading = true; STORE.commitsError = ''; STORE.commits = null;
  if (current === 'releases') go('releases');
  try {
    const j = await contentFetch(CONTENT_BASE + '/commits?per=12');
    STORE.commits = j.commits || [];
  } catch(e){ STORE.commitsError = e.message || String(e) }
  STORE.commitsLoading = false;
  if (current === 'releases') go('releases');
}
async function doPublish(action){
  if (action === 'rollback'){
    if (!canRollback()){ alert('回滚仅 boss 可用'); return }
    if (!confirm('回滚会把线上整体退回旧版（草稿将被线上内容覆盖，可能连带撤掉别人刚发布的内容）。确认回滚？')) return;
  } else {
    if (!confirm('发布 = 把草稿（cms 分支）合入 main 并触发构建，六项闸门全过才上线，约 2-3 分钟。确认发布？')) return;
  }
  try {
    const j = await contentFetch(CONTENT_BASE + '/publish', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action || 'publish' })
    });
    STORE.publishMsg = j.dispatched
      ? '已触发构建（' + new Date().toLocaleTimeString('zh-CN') + '）。约 2-3 分钟后上线；完成后回本页点「刷新对比」，草稿与线上应变为一致，版本串也会更新。'
      : '返回异常：' + JSON.stringify(j).slice(0, 160);
  } catch(e){ STORE.publishMsg = '发布失败：' + (e.message || String(e)) }
  if (current === 'changes') go('changes');
}

/* ── 编辑器 / 变更按钮的全局事件委托 ─────────────────────────── */
document.addEventListener('input', e => {
  if (!ED) return;
  const el = e.target.closest('[data-ed]');
  if (!el) return;
  let v = el.value;
  if (el.dataset.edtype === 'num'){ const n = Number(v); if (v.trim() !== '' && !isNaN(n)) v = n; }
  if (el.dataset.edtype === 'bool') v = (v === 'true');
  edSet(ED.doc, JSON.parse(el.dataset.ed), v);
});
document.addEventListener('click', e => {
  const opener = e.target.closest('[data-opened]');
  if (opener){ const a = JSON.parse(opener.dataset.opened); openEd(a[0], a[1], a[2]); return }
  const act = e.target.closest('[data-act]');
  if (act){
    const a = act.dataset.act;
    if (a === 'refreshChanges') refreshChanges();
    if (a === 'refreshCommits') refreshCommits();
    if (a === 'publish') doPublish('publish');
    if (a === 'rollback') doPublish('rollback');
    return;
  }
  if (!ED) return;
  const opBtn = e.target.closest('[data-edop]');
  if (!opBtn) return;
  const op = opBtn.dataset.edop, i = parseInt(opBtn.dataset.edi, 10);
  const arrPath = JSON.parse(opBtn.dataset.edlist);
  const list = edGet(ED.doc, arrPath);
  if (op === 'up' && i > 0){ const t = list[i-1]; list[i-1] = list[i]; list[i] = t }
  else if (op === 'down' && i < list.length - 1){ const t = list[i+1]; list[i+1] = list[i]; list[i] = t }
  else if (op === 'dup'){ list.splice(i + 1, 0, JSON.parse(JSON.stringify(list[i]))) }
  else if (op === 'del'){ if (!confirm('删除第 ' + i + ' 项？点「保存到草稿」后才会真正写入。')) return; list.splice(i, 1) }
  else if (op === 'add'){ list.push(list.length ? edBlank(JSON.parse(JSON.stringify(list[list.length - 1]))) : '') }
  else return;
  edRender();
});
document.getElementById('edClose').onclick = closeEd;
document.getElementById('edMask').onclick = closeEd;
document.getElementById('edSave').onclick = saveEd;

/* ── 启动：有会话就恢复（过期先续），没有就停在登录页 ── */""", 'editor_js')

# ═══ 5. 编辑器浮层 HTML（插在 main 之后）══════════════════════════
rep('<main class="main" id="view" tabindex="-1"></main>',
'''<main class="main" id="view" tabindex="-1"></main>

<!-- ═══════════════ 通用编辑器浮层 ═══════════════ -->
<div id="edWrap" hidden>
  <div class="ed-mask" id="edMask"></div>
  <div class="ed-panel">
    <div class="ed-head">
      <span class="t" id="edTitle">编辑</span>
      <button class="btn ghost sm" id="edClose">关闭</button>
      <button class="btn gold sm" id="edSave">保存到草稿</button>
    </div>
    <div class="ed-body" id="edBody"></div>
    <div class="ed-msg" id="edMsg"></div>
  </div>
</div>''', 'editor_html')

# ═══ 6. go() 挂首次加载触发 ═══════════════════════════════════════
rep("""  document.querySelectorAll('#view [data-go]').forEach(b => b.onclick = () => go(b.dataset.go));
  location.hash = '#/' + id;
}""",
"""  document.querySelectorAll('#view [data-go]').forEach(b => b.onclick = () => go(b.dataset.go));
  if (id === 'changes' && !STORE.changes && !STORE.changesLoading && !STORE.changesError) refreshChanges();
  if (id === 'releases' && !STORE.commits && !STORE.commitsLoading && !STORE.commitsError) refreshCommits();
  location.hash = '#/' + id;
}""", 'go_hooks')

# ═══ 7. 整个 VIEWS 块替换 ═════════════════════════════════════════
i = src.index('const VIEWS = {')
j = src.index('};' + chr(10) + chr(10) + 'const META = {', i)
NEW_VIEWS = r'''const VIEWS = {

  overview: () => {
    const pr = productsDoc(), ins = insightsDoc(), hm = homeDoc();
    const prods = (pr && pr.products) || [];
    const cats  = (pr && pr.categories) || [];
    const notes = (ins && ins.notes) || [];
    const pub   = notes.filter(n => (n.status || '') === 'published').length;
    const blocks = hm ? Object.keys(hm).filter(k => k !== 'meta' && !k.startsWith('_')) : [];
    const qs = STORE.inquiries || [];
    const countries = new Set(qs.map(q => q.country).filter(Boolean)).size;
    return `
    <div class="view-head">
      <div class="lead"><span class="num">01 / OVERVIEW</span><h1>总览</h1></div>
      <div class="side">${srcTag()}</div>
    </div>
    <div class="grid g4 sec">
      <div class="metric"><div class="k">产品</div><div class="v">${prods.length || '-'}</div><div class="d">${cats.length || '-'} 个分类</div></div>
      <div class="metric"><div class="k">文章</div><div class="v">${notes.length || '-'}</div><div class="d">${pub} 篇已发布</div></div>
      <div class="metric"><div class="k">栏目页 / 首页区块</div><div class="v">${PAGE_SLUGS.length}</div><div class="d">首页 ${blocks.length || '-'} 个区块</div></div>
      <div class="metric"><div class="k">询盘（本次读取）</div><div class="v">${STORE.inquiriesError ? '-' : qs.length}</div><div class="d">${STORE.inquiriesError ? '读取失败' : '来自 ' + countries + ' 个国家'}</div></div>
    </div>
    ${errorsNotice()}
    <div class="notice gold sec">
      <b>内容真源在仓库里 · 现在可以直接改</b>
      后台改的是 <code class="mono">content/*.json</code> 与 <code class="mono">data/products.json</code>：
      产品 / 文章 / 栏目页 / 首页 / 认证的条目行尾都有「改」按钮，点开即编辑；保存进草稿（cms 分支），
      到「变更清单」过目后点发布，构建器跑完闸门自动上线。页面 HTML 永远不会被后台直接改写。
      当前线上版本串 <code class="mono">${STORE.version}</code> 读自 <code class="mono">build/version.txt</code>。
    </div>
    <div class="split sec">
      <div class="panel">
        <div class="panel-h"><span class="ttl">发布链路</span><span class="grow"></span>
          <button class="btn ghost sm" data-go="changes">去发布</button></div>
        <div class="panel-b">
          <p class="p" style="margin:0 0 10px"><strong>已接入。</strong>编辑 → 保存草稿（cms 分支）→「变更清单」对比过目 →
          确认发布：合入 main · 升版本串 · 六项闸门 · Cloudflare Pages 自动上线，全程留痕可回滚。</p>
          <p class="mono dim" style="font-size:11px;margin:0">Worker /content 读写草稿 · /changes 对比 · /publish 触发构建 · Actions 六闸门</p>
        </div>
      </div>
      <div class="panel">
        <div class="panel-h"><span class="ttl">当前版本</span></div>
        <div class="panel-b stack">
          <div><span class="mono" style="color:var(--ok)">${STORE.version}</span>
            <div class="mono dim" style="font-size:11px">build/version.txt · ${STORE.loadedAt ? new Date(STORE.loadedAt).toLocaleString('zh-CN') : '-'}</div>
            <div style="font-size:13px">仓库里的内容快照</div></div>
          ${STORE.inquiriesError
            ? '<div class="notice" style="margin:0"><b>询盘读不到</b><span class="mono" style="font-size:12px">' + esc(STORE.inquiriesError) + '</span></div>'
            : '<div style="font-size:13px">询盘链路正常 · 最近 ' + qs.length + ' 条</div>'}
        </div>
      </div>
    </div>`;
  },

  products: () => {
    const pr = productsDoc();
    const prods = (pr && pr.products) || [];
    const cats  = (pr && pr.categories) || [];
    const cnt = {};
    prods.forEach(p => cnt[p.category] = (cnt[p.category] || 0) + 1);
    const catName = s => { const c = cats.find(c => c.slug === s); return c ? (c.short || c.en || s) : (s || '-') };
    const prodRows = prods.map((p, i) => row(
      [esc(p.sku), esc(p.nameEn), esc(catName(p.category)),
       String(p.status || '').toUpperCase() === 'OK' ? ['ok', '已发布'] : ['draft', (p.status || '未标状态')],
       p.moq == null ? '-' : String(p.moq),
       pr ? edBtn('data/products.json', ['products', i], '产品 · ' + (p.sku || i)) : '-'],
      { kAt:[0], dotAt:3, numAt:4 })).join('');
    const catRows = cats.map((c, ci) => row(
      [esc(c.slug), esc(c.en || '-'), esc(c.short || '-'), String(cnt[c.slug] || 0), String(((c.bullets) || []).length),
       pr ? edBtn('data/products.json', ['categories', ci], '分类 · ' + c.slug) : '-'],
      { kAt:[0], numAt:[3,4] })).join('');
    return `
    <div class="view-head">
      <div class="lead"><span class="num">02 / PRODUCTS</span><h1>产品与分类</h1></div>
      <div class="side">${prods.length} 款 · ${cats.length} 类<br>${srcTag()}</div>
    </div>
    <div class="notice gold sec">
      <b>怎么改</b>
      点行尾「改」进入编辑器：<strong>文案值随便改</strong>（名称、卖点、MOQ、交期、质保……）；
      <strong>结构键动前想清楚</strong> —— sku / slug / category 牵动页面链接与归组，status 是数据完备度标记不是上架开关。
      保存进的是草稿，「变更清单」过目后发布才上线。
    </div>
    <div class="panel sec">
      <div class="panel-h"><span class="ttl">型号 · ${prods.length}</span></div>
      <table class="tbl">${head(['SKU','型号名称','分类','数据状态','MOQ','编辑'],[4])}
        <tbody>${prodRows || '<tr><td colspan="6" class="empty">读不到产品数据</td></tr>'}</tbody>
      </table>
    </div>
    <div class="panel sec">
      <div class="panel-h"><span class="ttl">分类 · ${cats.length}</span></div>
      <table class="tbl">${head(['SLUG','分类名','短名','在架款数','要点数','编辑'],[3,4])}
        <tbody>${catRows || '<tr><td colspan="6" class="empty">读不到分类数据</td></tr>'}</tbody>
      </table>
    </div>
    <div class="notice sec">
      <b>分类是一份数据、两处使用</b>
      改一次分类名，首页分类卡与 /products/ 总览页同时生效 —— 发布前请在预览里两页都看一眼。
      「在架款数」按 category 归组现算，改了归组它会自己变。
    </div>`;
  },

  notes: () => {
    const ins = insightsDoc();
    const notes = (ins && ins.notes) || [];
    const rows = notes.map((n, ni) => row(
      [esc(n.ix || '-'), esc(n.title || '-'),
       (n.status === 'published' ? ['ok','已发布'] : ['draft', n.status || '草稿']),
       esc(n.date || '-'), n.readMins == null ? '-' : (n.readMins + ' 分钟'),
       ins ? edBtn('build/data/insights.json', ['notes', ni], '文章 · ' + (n.title || n.ix)) : '-'],
      { kAt:[0], dotAt:2, numAt:4 })).join('');
    return `
    <div class="view-head">
      <div class="lead"><span class="num">06 / NOTES</span><h1>文章</h1></div>
      <div class="side">${notes.length} 篇<br>${srcTag()}</div>
    </div>
    <div class="panel sec">
      <table class="tbl">${head(['编号','标题','状态','日期','篇幅','编辑'],[4])}
        <tbody>${rows || '<tr><td colspan="6" class="empty">读不到文章数据</td></tr>'}</tbody>
      </table>
    </div>
    <div class="notice gold sec">
      <b>块编辑已开放</b>
      点行尾「改」：标题 / 日期 / 状态 / 摘要直接改；正文是 blocks[]（h2 / p / ul / ol / table / notice），
      每块一项，可改可增可删可调序。发布后列表页、详情页与 JSON-LD 同步更新 —— 一份数据两处渲染。
    </div>
    <div class="pair sec">
      <div><div class="k">列表页头（标题 / 导语）</div>${ins ? edBtn('build/data/insights.json', ['hub'], '文章页头 hub') : '-'}</div>
      <div><div class="k">目录卡（产品手册 PDF 的文案）</div>${ins ? edBtn('build/data/insights.json', ['catalogue'], '目录卡 catalogue') : '-'}</div>
    </div>`;
  },

  pages: () => {
    const rows = PAGE_SLUGS.map(s => {
      const d = pageDoc(s);
      const editCell = edBtn('content/pages/' + s + '.json', [], '栏目页 · ' + s);
      if (!d) return row([esc('/' + s + '/'), '读不到内容', '-', ['risk','缺失'], editCell], { kAt:[0], numAt:2, dotAt:3 });
      const m = d.meta || {};
      return row([esc(m.path || ('/' + s + '/')), esc(m.title || '-'), blockCount(d),
                  d._rules ? ['ok','含规则'] : ['ok','已就位'], editCell],
                 { kAt:[0], numAt:2, dotAt:3 });
    }).join('');
    return `
    <div class="view-head">
      <div class="lead"><span class="num">07 / PAGES</span><h1>栏目页</h1></div>
      <div class="side">${PAGE_SLUGS.length} 个页面<br>${srcTag()}</div>
    </div>
    <div class="panel sec">
      <table class="tbl">${head(['页面','SEO 标题','区块数','状态','编辑'],[2])}
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="notice gold sec">
      <b>整页编辑</b>
      点行尾「改」打开该页完整文案树：meta（SEO 标题 / 描述）、各区块的字段与列表都能改。
      「区块数」是按顶层字段现算的，加删区块它会自己变。说明性字段（下划线开头）只读展示，防手滑。
    </div>`;
  },

  home: () => {
    const hm = homeDoc();
    if (!hm) return VIEWS._placeholder('home', '首页', '读不到 <code class="mono">content/home.json</code>。');
    const blocks = Object.keys(hm).filter(k => k !== 'meta' && !k.startsWith('_'));
    const faq = (hm.faq && hm.faq.items) || [];
    const rows = blocks.map(k => {
      const v = hm[k];
      const n = (v && typeof v === 'object') ? Object.keys(v).filter(x => !x.startsWith('_')).length : 1;
      const kind = Array.isArray(v) ? '列表' : (v && typeof v === 'object' ? '区块' : '文本');
      return row([esc(k), kind, n, edBtn('content/home.json', [k], '首页 · ' + k)], { kAt:[0], numAt:2 });
    }).join('');
    return `
    <div class="view-head">
      <div class="lead"><span class="num">08 / HOME</span><h1>首页</h1></div>
      <div class="side">${blocks.length} 个区块<br>${srcTag()}</div>
    </div>
    <div class="notice gold sec">
      <b>FAQ 是一份数据、两处渲染</b>
      当前有 <strong>${faq.length} 条 FAQ</strong>：页面可见那份与 JSON-LD 那份同出 <code class="mono">faq.items</code>。
      改这一处，两处同步。编辑：点区块行尾「改」，或在 SEO meta 行改标题描述。
    </div>
    <div class="panel sec">
      <div class="panel-h"><span class="ttl">区块清单 · ${blocks.length}</span>
        <span class="grow"></span>${edBtn('content/home.json', ['meta'], '首页 · SEO meta')}</div>
      <table class="tbl">${head(['区块','类型','字段数','编辑'],[2])}
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="notice sec">
      <b>派生值不在这里</b>
      分类卡款数、洞察卡前 3 篇、OEM 八步、拼贴带的 300+ —— 全部由构建器现算，不要手填。
    </div>`;
  },

  certs: () => {
    const c = certDoc();
    if (!c) return VIEWS._placeholder('certs', '认证文件', '读不到 <code class="mono">content/pages/certifications.json</code>。');
    const d = c.documents || {};
    const sec = (c.documentsSection && c.documentsSection.h2) || '-';
    return `
    <div class="view-head">
      <div class="lead"><span class="num">09 / CERTIFICATES</span><h1>认证文件</h1></div>
      <div class="side">${d.count || '-'} 份<br>${srcTag()}</div>
    </div>
    <div class="panel sec">
      <div class="panel-h"><span class="ttl">文件清单（按模板渲染）</span><span class="grow"></span>
        ${edBtn('content/pages/certifications.json', [], '认证页整页')}</div>
      <table class="tbl">${head(['项','值'])}
        <tbody>
          ${row(['份数', String(d.count == null ? '-' : d.count)])}
          ${row(['路径模板', '<code class="mono">' + esc(d.path || '-') + '</code>'])}
          ${row(['替代文本模板', esc(d.alt || '-')])}
          ${row(['尺寸', (d.width ? d.width + ' × ' + d.height : '-')])}
          ${row(['区块标题', esc(sec)])}
          ${row(['换图方式', '同名替换 cert-01 … cert-' + String(d.count || 0).padStart(2,'0')])}
        </tbody>
      </table>
    </div>
    <div class="notice gold sec">
      <b>换证书的图不需要动这里</b>
      同名替换 <code class="mono">cert-01…16.png</code> 即可（图片仍在仓库 / R2，不在本编辑器范围）。
      这页的文案字段可改，但配题按「文件类型」走的约定优先于逐张手填。
    </div>`;
  },

  inquiries: () => {
    if (STORE.inquiriesError) return `
      <div class="view-head">
        <div class="lead"><span class="num">10 / INQUIRIES</span><h1>询盘查看</h1></div>
        <div class="side"><span class="tag ro">只读</span></div>
      </div>
      <div class="notice sec" style="border-color:var(--warn)">
        <b>这份数据没读到</b>
        <div class="mono" style="font-size:12px;margin-top:6px">${esc(STORE.inquiriesError)}</div>
        <div style="margin-top:8px">这里不会用演示数据冒充 —— 读不到就如实说读不到。
        常见原因：Supabase 会话过期（刷新页面会先自动续期再重放），或被本机代理改了 TLS。</div>
      </div>`;
    const qs = STORE.inquiries || [];
    const st = s => (s === 'new' ? ['new', s] : ['ok', s || '-']);
    const rows = qs.map(q => row(
      [esc(String(q.created_at || '').replace('T',' ').slice(0,16)), esc(q.name || '-'),
       esc(q.company || '-'), esc(q.country || '-'), st(q.status)],
      { kAt:[0], dotAt:4 })).join('');
    const countries = new Set(qs.map(q => q.country).filter(Boolean)).size;
    const news = qs.filter(q => (q.status || '') === 'new').length;
    return `
    <div class="view-head">
      <div class="lead"><span class="num">10 / INQUIRIES</span><h1>询盘查看</h1></div>
      <div class="side"><span class="tag ro">只读</span><br>处理与跟单请到外贸作战中心</div>
    </div>
    <div class="notice gold">
      <b>这里为什么是只读的</b>
      买家状态（新 / 已联系 / 报价中 / 已成交）只在<strong>外贸作战中心</strong>修改。
      如果两处都能改，同一笔询盘的状态会互相覆盖。这个页面给运营人员看的是「市场反馈」，不是「跟进工具」。
    </div>
    <div class="grid g3 sec">
      <div class="metric"><div class="k">本次读取</div><div class="v">${qs.length}</div><div class="d">最多 50 条</div></div>
      <div class="metric"><div class="k">状态为 new</div><div class="v">${news}</div><div class="d">待业务员处理</div></div>
      <div class="metric"><div class="k">国家数</div><div class="v">${countries}</div><div class="d">按本次结果现算</div></div>
    </div>
    <div class="panel">
      <table class="tbl">${head(['时间','买家','公司','国家','状态'])}
        <tbody>${rows || '<tr><td colspan="5" class="empty">表里暂时没有询盘</td></tr>'}</tbody>
      </table>
    </div>
    <p class="mono dim" style="font-size:11px;margin-top:10px">
      与作战中心同一数据源 · 此处不可修改、不提供导出 · 统计口径是本次读取的 ${qs.length} 条，不是「近 30 天」
    </p>`;
  },

  changes: () => {
    const list = STORE.changes || [];
    const err = STORE.changesError;
    const changed = list.filter(f => f.changed && !f.error);
    const rows = list.map(f => {
      const st = f.error ? ['risk','读取失败'] : (f.changed ? ['new','待发布'] : ['ok','一致']);
      return row([esc(f.path),
                  f.main ? '<span class="mono">有</span>' : '<span class="mono dim">缺</span>',
                  f.cms ? '<span class="mono">有</span>' : '<span class="mono dim">缺</span>',
                  st], { kAt:[0], dotAt:3 });
    }).join('');
    return `
    <div class="view-head">
      <div class="lead"><span class="num">04 / CHANGES</span><h1>变更清单</h1></div>
      <div class="side">${STORE.changesLoading ? '对比中…' : (changed.length ? '<span style="color:var(--warn)">' + changed.length + ' 个文件待发布</span>' : '草稿与线上一致')}<br>${srcTag()}</div>
    </div>
    ${err ? '<div class="notice sec" style="border-color:var(--warn)"><b>对比没做成</b><div class="mono" style="font-size:12px;margin-top:6px">' + esc(err) + '</div></div>' : ''}
    <div class="panel sec">
      <div class="panel-h"><span class="ttl">草稿（cms 分支）vs 线上（main）</span><span class="grow"></span>
        <button class="btn ghost sm" data-act="refreshChanges">${STORE.changesLoading ? '对比中…' : '刷新对比'}</button></div>
      <table class="tbl">${head(['文件','线上','草稿','状态'])}
        <tbody>${rows || '<tr><td colspan="4" class="empty">' + (STORE.changesLoading || err ? '—' : '正在对比…') + '</td></tr>'}</tbody>
      </table>
    </div>
    <div class="release sec">
      <div class="release-h">
        <span class="num">RELEASE</span>
        <div class="ttl">发布到生产环境</div>
        <div class="meta">当前线上 ${STORE.version} · ${changed.length} 个文件待发布</div>
      </div>
      <div class="release-b">
        <div>
          <span class="num">发布会自动跑的闸门</span>
          <ul class="gates">
            ${[['公共段无漂移','39 页 × 4 段字节级'],['标签配平正常','开闭相等'],
               ['站内断链为 0','全站链接'],['渲染可见中文为 0','除预览条'],
               ['禁写清单扫描','按语境判读'],['版本串递增','发布时自动']]
              .map(g => '<li><span class="dot new"></span><span class="t">' + g[0] + '</span><span class="m">' + g[1] + '</span></li>').join('')}
          </ul>
          <div class="notice gold" style="margin-bottom:0"><b>发布不限角色 · 闸门是唯一的自动护栏</b>
          任何一项不过，构建直接失败、线上不动。</div>
        </div>
      </div>
      <div class="release-f">
        <span class="mono dim" style="font-size:11px">构建约 2-3 分钟 · 完成后版本串更新</span>
        <span class="grow"></span>
        ${canRollback() ? '<button class="btn ghost sm" data-act="rollback">回滚到线上版</button>' : ''}
        <button class="btn gold" data-act="publish"${changed.length ? '' : ' disabled title="草稿与线上一致，没有可发布的内容"'}>确认发布</button>
      </div>
    </div>
    ${STORE.publishMsg ? '<div class="notice safe sec"><b>发布状态</b>' + esc(STORE.publishMsg) + '</div>' : ''}
    <div class="notice sec">
      <b>「发布」做了什么</b>
      合并 cms → main · 升版本串 · 构建器重出 39 页 · 六项闸门 · 提交推送 · Cloudflare Pages 自动上线。
      每次发布都是一次提交，全流程留痕。
    </div>`;
  },

  releases: () => {
    const err = STORE.commitsError;
    const cs = STORE.commits || [];
    const rows = cs.map(c => row(
      ['<span class="mono">' + esc(c.sha || '-') + '</span>',
       esc(String(c.date || '').replace('T', ' ').slice(0, 16)),
       esc(c.message || '-'), esc(c.author || '-')],
      {})).join('');
    return `
    <div class="view-head">
      <div class="lead"><span class="num">05 / RELEASES</span><h1>发布历史</h1></div>
      <div class="side">${srcTag()}</div>
    </div>
    <div class="panel sec">
      <div class="panel-h"><span class="ttl">main 分支最近提交</span><span class="grow"></span>
        <button class="btn ghost sm" data-act="refreshCommits">刷新</button></div>
      <table class="tbl">${head(['提交','时间','说明','作者'])}
        <tbody>${rows || '<tr><td colspan="4" class="empty">' + (STORE.commitsLoading ? '正在读取…' : (err ? esc(err) : '—')) + '</td></tr>'}</tbody>
      </table>
    </div>
    <div class="notice sec">
      <b>每次发布都是一次提交</b>
      版本串升一节，内容改动全部可追溯。发错了优先「再发一版修正」—— 影响面只有一次修改。
    </div>
    <div class="notice gold sec">
      <b>当前角色 ${SESSION ? (SESSION.role || '-') : '-'} · 回滚${canRollback() ? '可用' : '不可用'}</b>
      规则是<strong>发布不限角色、回滚仅 boss</strong>：回滚会让线上<strong>整体退回</strong>旧版（可能连带撤掉别人刚发布的内容），所以单独收口。
      ${canRollback() ? '回滚入口在「变更清单」页。' : '你不是 boss（' + ((SESSION && SESSION.role) || '-') + '），回滚入口不对你开放。'}
    </div>`;
  },

  _placeholder: (id, label, note) => `
    <div class="view-head">
      <div class="lead"><span class="num">${id.toUpperCase()}</span><h1>${label}</h1></div>
      <div class="side">${srcTag()}</div>
    </div>
    <div class="panel sec"><div class="empty">
      ${note || '本页在后续迭代实现'}
    </div></div>`
};'''

src = src[:i] + NEW_VIEWS + src[j:]
print('OK [views 整块替换]')

assert src != orig
io.open(P, 'w', encoding='utf-8').write(src)
print('index.html 补丁完成')
