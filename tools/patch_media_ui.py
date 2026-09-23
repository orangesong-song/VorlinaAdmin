# -*- coding: utf-8 -*-
"""
vadmin-013 · 后台媒体库（上传）前端

与 Worker /media/* 配套。三条纪律：
1. **图片基址统一走 imgSrc()** —— 上传过的走 Worker 直读（R2，立刻可见），
   其余走官网域（vorlina.net，零额外请求）。不做判断就会出现
   「刚上传的图在产品页预览裂开」，因为那张图还只在 cms 分支。
2. **上传 = 草稿**：图进 cms 分支，不碰 main，与内容草稿同一条闸门。
3. **仓库图库只读**：换图靠同名覆盖，不在后台做删除（删官网真源风险高）。
"""
import io, os

F = '/Volumes/我的文件/WorkBuddy/sitebuilding/vorlina-admin/index.html'
s = io.open(F, encoding='utf-8').read()


def rep(old, new, tag, cnt=1):
    global s
    n = s.count(old)
    assert n == cnt, '[%s] 期望 %d 处，实际 %d 处' % (tag, cnt, n)
    s = s.replace(old, new, cnt)
    print('  ok', tag)


# ── ① CSS ────────────────────────────────────────────────────────────
rep("""  .pcard-f{display:flex;align-items:center;gap:8px;padding:9px 13px;border-top:1px solid var(--line)}""",
    """  .pcard-f{display:flex;align-items:center;gap:8px;padding:9px 13px;border-top:1px solid var(--line)}
  /* ── 媒体库（vadmin-013）── */
  .mzone{border:1px dashed var(--line);background:rgba(0,0,0,.02);padding:20px 16px;text-align:center;font-size:13px;color:var(--muted);line-height:1.9}
  .mzone.hot{border-color:var(--gold);background:var(--gold-soft);color:var(--ink)}
  .mzone b{color:var(--ink)}
  .mzone-n{font-size:11.5px;color:var(--muted);margin-top:4px}
  .msec-h{font-size:12px;letter-spacing:.08em;color:var(--muted);border-bottom:1px solid var(--line);padding:0 0 6px;margin:22px 0 0}
  .mgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(166px,1fr));gap:12px;margin-top:12px}
  .mcard{border:1px solid var(--line);background:#fff;display:flex;flex-direction:column}
  .mcard-thumb{height:110px;background:#F5F3EF;display:flex;align-items:center;justify-content:center;overflow:hidden}
  .mcard-thumb img{max-width:100%;max-height:100%;object-fit:contain;display:block}
  .mcard-b{padding:8px 10px;flex:1}
  .mcard-n{font-size:12px;line-height:1.4;color:var(--ink);word-break:break-all}
  .mcard-s{font-size:11px;color:var(--muted);margin-top:3px}
  .mcard-f{display:flex;gap:8px;padding:7px 10px;border-top:1px solid var(--line)}""",
    'CSS')

# ── ② 状态与图片基址 ─────────────────────────────────────────────────
rep("""const IMG_BASE = 'https://vorlina.net';""",
    """const IMG_BASE = 'https://vorlina.net';
/* ── 媒体库（vadmin-013）──────────────────────────────────────────
   MEDIA_UPLOADED = 后台上传过的文件名集合（来自 GET /media/list）。
   为什么需要它：上传的图**只进 cms 分支**，线上 vorlina.net 此刻还没有 ——
   若一律拼 IMG_BASE，运营上传完在产品页看到的就是裂图。
   所以：上传过的走 Worker 直读（R2 命中即出），其余走官网域（零额外请求）。 */
const MEDIA = { items:[], loaded:false, loading:false, error:'', msg:'', msgKind:'', busy:false };
const MEDIA_UPLOADED = new Set();
function baseName(p){ return String(p || '').split('/').pop() }
function imgSrc(fileName, siteRel){
  const fn = baseName(fileName);
  if (fn && MEDIA_UPLOADED.has(fn)) return CONTENT_BASE + '/media/file/img/' + encodeURIComponent(fn);
  return IMG_BASE + (siteRel || '');
}
async function mediaLoad(){
  if (MEDIA.loading) return;
  MEDIA.loading = true;
  try {
    const j = await contentFetch(CONTENT_BASE + '/media/list');
    if (j && j.ok){
      MEDIA.items = j.items || [];
      MEDIA.error = j.warning === 'r2_not_bound' ? 'Worker 还没绑定 R2 桶 —— 现在只能看仓库已有的图，上传不可用（见部署文档第 ⑥ 节）。' : '';
    } else {
      MEDIA.error = '媒体列表读不到：' + ((j && j.error) || '未知原因');
    }
  } catch(e){ MEDIA.error = '媒体列表读不到：' + (e && e.message || e) }
  MEDIA.loading = false; MEDIA.loaded = true;
  MEDIA_UPLOADED.clear();
  (MEDIA.items || []).forEach(it => MEDIA_UPLOADED.add(it.name));
}
function repoImageList(){
  const out = new Map();
  const img = STORE.files['build/data/imagery.json'];
  if (img) for (const k of Object.keys(img)){
    const g = img[k] || {};
    for (const it of (g.items || [])) if (it && it.src) out.set(it.src, it.url || '');
  }
  return Array.from(out.entries()).sort((a, b) => (a[0] < b[0] ? -1 : 1));
}
function mSize(n){
  if (!n && n !== 0) return '';
  return n > 1024 * 1024 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';
}
function mcard(m, uploaded){
  const url = uploaded ? CONTENT_BASE + '/media/file/img/' + encodeURIComponent(m.name) : imgSrc(m.name, m.url);
  const ops = uploaded
    ? '<button class="btn ghost sm" data-copy="' + escAttr(m.name) + '">复制文件名</button>'
      + '<button class="btn ghost sm risk" data-mdel="' + escAttr(m.key || ('img/' + m.name)) + '">移除</button>'
    : '<button class="btn ghost sm" data-copy="' + escAttr(m.name) + '">复制文件名</button>';
  return '<div class="mcard"><div class="mcard-thumb"><img src="' + escAttr(url) + '" loading="lazy"'
    + ' onerror="this.style.display=\\'none\\'"></div>'
    + '<div class="mcard-b"><div class="mcard-n mono">' + esc(m.name) + '</div>'
    + '<div class="mcard-s">' + (uploaded ? esc(mSize(m.size)) + ' · 已上传' : '仓库图 · 只读') + '</div></div>'
    + '<div class="mcard-f">' + ops + '</div></div>';
}
async function mediaUploadFiles(files){
  if (!files || !files.length) return;
  MEDIA.busy = true; MEDIA.msg = '正在上传 ' + files.length + ' 个文件…'; MEDIA.msgKind = '';
  rerenderMedia();
  const done = [], failed = [];
  for (const f of files){
    const fd = new FormData();
    fd.append('file', f, f.name);
    try {
      const res = await fetch(CONTENT_BASE + '/media/upload', {
        method: 'POST', headers: { Authorization: 'Bearer ' + sbToken() }, body: fd
      });
      const t = await res.text();
      let j = null; try { j = JSON.parse(t) } catch(e){}
      if (res.ok && j && j.ok){
        done.push(j.name || f.name);
        if (j.gh && !j.gh.ok) failed.push((j.name || f.name) + '（已进媒体库，但写仓库失败：' + (j.gh.error || '') + '）');
      } else {
        failed.push((f.name || '(未命名)') + '（' + ((j && j.error) || 'HTTP ' + res.status) + '）');
      }
    } catch(e){ failed.push((f.name || '(未命名)') + '（网络错误）') }
  }
  await mediaLoad();
  MEDIA.busy = false;
  const parts = [];
  if (done.length) parts.push('已上传 ' + done.length + ' 个：' + done.join('、'));
  if (failed.length) parts.push('失败 ' + failed.length + ' 个：' + failed.join('；'));
  MEDIA.msg = parts.join('　｜　');
  MEDIA.msgKind = failed.length ? 'gold' : 'safe';
  rerenderMedia();
}
function rerenderMedia(){
  if (current !== 'media') return;
  document.getElementById('view').innerHTML = render('media');
  bindMedia();
}
function bindMedia(){
  const zone = document.getElementById('mzone');
  const input = document.getElementById('mfile');
  const pick = document.getElementById('mpick');
  if (!zone) return;
  if (pick) pick.onclick = () => input && input.click();
  if (input) input.onchange = () => { mediaUploadFiles(Array.from(input.files || [])); input.value = '' };
  ['dragenter','dragover'].forEach(ev => zone.addEventListener(ev, e => {
    e.preventDefault(); e.stopPropagation(); zone.classList.add('hot');
  }));
  ['dragleave','drop'].forEach(ev => zone.addEventListener(ev, e => {
    e.preventDefault(); e.stopPropagation(); zone.classList.remove('hot');
  }));
  zone.addEventListener('drop', e => {
    const fs = e.dataTransfer && e.dataTransfer.files;
    if (fs && fs.length) mediaUploadFiles(Array.from(fs));
  });
  document.querySelectorAll('#view [data-copy]').forEach(b => b.onclick = async () => {
    const t = b.dataset.copy;
    try { await navigator.clipboard.writeText(t) } catch(e){ window.prompt('复制这个文件名：', t) }
    const old = b.textContent; b.textContent = '已复制'; setTimeout(() => { b.textContent = old }, 1200);
  });
  document.querySelectorAll('#view [data-mdel]').forEach(b => b.onclick = async () => {
    const key = b.dataset.mdel;
    if (!confirm('从后台媒体库移除这个文件？\n\n' + key + '\n\n仓库里的同名文件不会被删除。')) return;
    try {
      const res = await fetch(CONTENT_BASE + '/media/file/' + key.split('/').map(encodeURIComponent).join('/'),
        { method: 'DELETE', headers: { Authorization: 'Bearer ' + sbToken() } });
      const j = await res.json().catch(() => ({}));
      MEDIA.msg = (j && j.ok) ? '已移除：' + key : '移除失败：' + ((j && j.error) || res.status);
      MEDIA.msgKind = (j && j.ok) ? 'safe' : 'gold';
    } catch(e){ MEDIA.msg = '移除失败：' + (e && e.message || e); MEDIA.msgKind = 'gold' }
    await mediaLoad(); rerenderMedia();
  });
}""",
    '状态与工具函数')

# ── ③ 图片基址统一（5 处）────────────────────────────────────────────
rep("""  return '<div class="ed-thumb' + (hero ? ' hero' : '') + '"><img src="' + escAttr(IMG_BASE + u) + '" loading="lazy" onerror="this.style.display=\\'none\\'">""",
    """  return '<div class="ed-thumb' + (hero ? ' hero' : '') + '"><img src="' + escAttr(imgSrc(u, u)) + '" loading="lazy" onerror="this.style.display=\\'none\\'">""",
    'edThumb 基址')
rep("""  const u = fn ? map[fn] : '';
  return u ? IMG_BASE + u : '';""",
    """  const u = fn ? map[fn] : '';
  return u ? imgSrc(u, u) : '';""",
    'prodHeroUrl 基址')
rep("""  const u = c.cardImage ? IMG_BASE + '/assets/img/' + c.cardImage : '';""",
    """  const u = c.cardImage ? imgSrc(c.cardImage, '/assets/img/' + c.cardImage) : '';""",
    '分类卡片基址')
rep("""  const url = c.cardImage ? IMG_BASE + '/assets/img/' + c.cardImage : '';""",
    """  const url = c.cardImage ? imgSrc(c.cardImage, '/assets/img/' + c.cardImage) : '';""",
    '分类编辑预览基址')
rep("""  const img = n.image ? IMG_BASE + n.image : '';""",
    """  const img = n.image ? imgSrc(n.image, n.image) : '';""",
    '文章配图基址')

# ── ④ VIEWS.media（插进 VIEWS 对象，放在 _placeholder 之前）──────────
rep("""  _placeholder: (id, label, note) => `""",
    """  media: () => {
    const up = MEDIA.items || [];
    const repo = repoImageList();
    const note = MEDIA.error
      ? '<div class="notice gold">' + esc(MEDIA.error) + '</div>'
      : (MEDIA.msg ? '<div class="notice ' + (MEDIA.msgKind || '') + '">' + esc(MEDIA.msg) + '</div>' : '');
    const upBody = up.length
      ? '<div class="mgrid">' + up.map(m => mcard(m, true)).join('') + '</div>'
      : '<div class="empty">还没有上传过文件 —— 把图片拖到上面的框里，或点「选择文件」。</div>';
    const repoBody = repo.length
      ? '<div class="mgrid">' + repo.map(([fn, url]) => mcard({ name: fn, url: url }, false)).join('') + '</div>'
      : '<div class="empty">图库没读到（imagery.json 未载入）。</div>';
    return `
    <div class="view-head">
      <div class="lead"><span class="num">MEDIA</span><h1>媒体库</h1></div>
      <div class="side">${srcTag()}</div>
    </div>
    <div class="panel sec">
      <div class="notice"><b>上传 = 草稿，不会直接上线</b>图会进 cms 分支（和内容草稿同一条闸门），
        必须走「变更清单 → 发布」才进官网。文件名建议用英文，换图就传<b>同名</b>文件覆盖。</div>
      ${note}
      <div class="mzone" id="mzone">
        <b>把图片拖到这里</b>　或　<button class="btn ghost sm" id="mpick"${MEDIA.busy ? ' disabled' : ''}>选择文件</button>
        <input type="file" id="mfile" multiple hidden
          accept="image/webp,image/jpeg,image/png,image/avif,image/gif,image/svg+xml,application/pdf">
        <div class="mzone-n">webp / jpg / png / avif / gif / svg / pdf，单张 ≤ 8MB</div>
      </div>
      <div class="msec-h">已上传 · 后台媒体库（${up.length}）</div>
      ${upBody}
      <div class="msec-h">仓库图库 · imagery.json（${repo.length}）</div>
      <div class="edsec-note">官网正在用的图，这里只读。点「复制文件名」后粘到产品的「图片」分区里即可引用。</div>
      ${repoBody}
    </div>`;
  },
  _placeholder: (id, label, note) => `""",
    'VIEWS.media')

# ── ⑤ go() 里绑定事件 ───────────────────────────────────────────────
rep("""  if (id === 'changes' && !STORE.changes && !STORE.changesLoading && !STORE.changesError) refreshChanges();""",
    """  if (id === 'media'){
    bindMedia();
    if (!MEDIA.loaded && !MEDIA.loading) mediaLoad().then(() => {
      MEDIA_UPLOADED.forEach(() => {});            /* 集合已在 mediaLoad 里刷新 */
      if (current === 'media'){ document.getElementById('view').innerHTML = render('media'); bindMedia(); }
    });
  }
  if (id === 'changes' && !STORE.changes && !STORE.changesLoading && !STORE.changesError) refreshChanges();""",
    'go() 绑定媒体事件')

# ── ⑥ META 文案同步（别让页面说谎）──────────────────────────────────
rep("""  media:{n:'媒体库', t:'图片与目录 PDF。P1 第二阶段接入 Cloudflare R2（现在图片仍在仓库里）。'},""",
    """  media:{n:'媒体库', t:'上传图片与目录 PDF。上传走 Worker 进 R2，并同步落 cms 分支，发布后才进官网。'},""",
    'META 文案')

io.open(F, 'w', encoding='utf-8').write(s)
print('已写入', F, '大小', os.path.getsize(F))
