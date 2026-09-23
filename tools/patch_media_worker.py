# -*- coding: utf-8 -*-
"""
vadmin-013 · Worker 新增 /media 路由（后台媒体库直传）

设计要点（写在代码里，也写在这里，防止后人误改）：
1. **双写，不换真源**：上传的图 ① 存 R2（后台预览 + 持久备份）② 同步 PUT 到 GitHub
   `cms` 分支的 `assets/img/<name>`。官网模板仍引用 `/assets/img/...`，构建照旧 ——
   **不改动官网架构**，这正是 A 路线「零架构手术」的前提。
2. **预览统一走 Worker**：`GET /media/file/img/<name>` 先查 R2，miss 则回源
   `https://vorlina.net/assets/img/<name>`。这样刚上传、还在 cms 分支（线上还没有）的图
   也能在后台立刻看到预览。
3. **读写鉴权分离**：list / upload / delete 必须 `requireMember`（Supabase JWT + members 表）；
   file 直读**免鉴权**，因为 <img src> 不会带 Authorization 头 —— 图片本就是公开资产。
4. **R2 未绑定时优雅降级**：返回 `r2_not_bound`，页面显示「未配置」而不是崩掉。
"""
import io, os

F = '/Volumes/我的文件/WorkBuddy/sitebuilding/vorlina-admin/deploy/worker.merged.js'
s = io.open(F, encoding='utf-8').read()


def rep(old, new, tag, cnt=1):
    global s
    n = s.count(old)
    assert n == cnt, '[%s] 期望 %d 处，实际 %d 处' % (tag, cnt, n)
    s = s.replace(old, new, cnt)
    print('  ok', tag)


# ── ① 路由分发 ────────────────────────────────────────────────────────
rep(
    """    // ⑤ 发布（触发 Actions workflow_dispatch）
    if (path === '/publish') {""",
    """    // ⑥ 媒体库（R2 直传 · 后台运营上传图片 / 目录 PDF）
    if (path === '/media/list') {
      if (request.method === 'GET') return handleMediaList(request, env);
      return json({ ok: false, error: 'method_not_allowed' }, 405, corsFor(request, env, 'content'));
    }
    if (path === '/media/upload') {
      if (request.method === 'POST') return handleMediaUpload(request, env);
      return json({ ok: false, error: 'method_not_allowed' }, 405, corsFor(request, env, 'content'));
    }
    // 直读**免鉴权**：<img src> 不会带 Authorization 头，图片本就是公开资产。
    if (path.startsWith('/media/file/')) {
      if (request.method === 'GET') return handleMediaFile(request, env);
      if (request.method === 'DELETE') return handleMediaDelete(request, env);
      return json({ ok: false, error: 'method_not_allowed' }, 405, corsFor(request, env, 'content'));
    }

    // ⑤ 发布（触发 Actions workflow_dispatch）
    if (path === '/publish') {""",
    '路由分发加 /media/*')

# ── ② 三个处理函数（追加到文件末尾）──────────────────────────────────
MEDIA_FN = r'''

/* ══════════════════════════════════════════════════════════════════════
   ⑥ 媒体库（R2 直传）—— 后台运营上传图片 / 目录 PDF
   ══════════════════════════════════════════════════════════════════════
   存储策略：**双写**
     · R2  bucket 绑定名 env.MEDIA —— 后台预览 + 持久备份
     · GitHub `cms` 分支 assets/img/<name> —— 官网构建的真源（模板引用 /assets/img/...）
   为什么不只存 R2：只存 R2 就得把官网所有 <img> 改成 CDN 绝对地址，属于架构手术；
   双写让「运营能上传」和「官网架构不变」同时成立。

   ⚠️ 图进的是 **cms 分支**，不是 main —— 和内容草稿同一条闸门，
      上传不会直接上线，必须走「变更清单 → 发布」才进 main。
   ══════════════════════════════════════════════════════════════════════ */

const MEDIA_TYPES = {
  'image/webp': 'webp', 'image/jpeg': 'jpg', 'image/png': 'png',
  'image/avif': 'avif', 'image/gif': 'gif', 'image/svg+xml': 'svg',
  'application/pdf': 'pdf'
};
const MEDIA_MAX = 8 * 1024 * 1024;          // 单文件 8MB（Worker 内存 + GitHub API 双重约束）
const MEDIA_PREFIX = 'img/';
const MEDIA_SITE = 'https://vorlina.net';   // 回源源站：R2 没有就问线上官网要

/* 文件名净化：挡路径穿越与危险字符，**保留中文**（CF Pages 与浏览器都能处理） */
function mediaSafeName(raw) {
  let n = String(raw || '').trim().replace(/[\\/]+/g, '-');
  n = n.replace(/[:*?"<>|\u0000-\u001f]+/g, '');
  n = n.replace(/\.\.+/g, '.');
  const i = n.lastIndexOf('.');
  let stem = i > 0 ? n.slice(0, i) : n;
  let ext  = i > 0 ? n.slice(i + 1).toLowerCase().replace(/[^a-z0-9]/g, '') : '';
  stem = stem.replace(/^\.+/, '').replace(/^[-\s]+|[-\s]+$/g, '');
  if (!stem) stem = 'file';
  if (stem.length > 80) stem = stem.slice(0, 80);
  return stem + (ext ? '.' + ext : '');
}

/* 分块转 base64 —— 一次性 apply 大数组会爆调用栈 */
function bytesToB64(u8) {
  let out = '';
  const CH = 0x8000;
  for (let i = 0; i < u8.length; i += CH) {
    out += String.fromCharCode.apply(null, u8.subarray(i, i + CH));
  }
  return btoa(out);
}

// GET /media/list → R2 里已上传的媒体（后台媒体库网格用）
async function handleMediaList(request, env) {
  const auth = await requireMember(request, env);
  if (!auth.ok) return json({ ok: false, error: auth.error }, 401, corsFor(request, env, 'content'));
  if (!env.MEDIA) return json({ ok: true, items: [], warning: 'r2_not_bound' }, 200, corsFor(request, env, 'content'));

  const l = await env.MEDIA.list({ prefix: MEDIA_PREFIX });
  const items = (l.objects || []).map(o => ({
    key: o.key,
    name: o.key.slice(MEDIA_PREFIX.length),
    size: o.size,
    uploaded: o.uploaded ? o.uploaded.toISOString() : '',
    url: '/media/file/' + o.key
  })).sort((a, b) => (a.uploaded < b.uploaded ? 1 : -1));
  return json({ ok: true, items }, 200, corsFor(request, env, 'content'));
}

// POST /media/upload  multipart/form-data: file=<二进制>[, name=<文件名>]
async function handleMediaUpload(request, env) {
  const auth = await requireMember(request, env);
  if (!auth.ok) return json({ ok: false, error: auth.error }, 401, corsFor(request, env, 'content'));
  if (!env.MEDIA) return json({ ok: false, error: 'r2_not_bound', hint: 'Worker 未绑定 R2 桶（变量名 MEDIA）' }, 503, corsFor(request, env, 'content'));

  let form;
  try { form = await request.formData(); }
  catch { return json({ ok: false, error: 'bad_form' }, 400, corsFor(request, env, 'content')); }

  const file = form.get('file');
  if (!file || typeof file === 'string') return json({ ok: false, error: 'missing_file' }, 400, corsFor(request, env, 'content'));

  const ctype = (file.type || '').toLowerCase();
  if (!MEDIA_TYPES[ctype]) {
    return json({ ok: false, error: 'bad_type', type: ctype, allow: Object.keys(MEDIA_TYPES) },
      415, corsFor(request, env, 'content'));
  }
  const buf = new Uint8Array(await file.arrayBuffer());
  if (buf.length > MEDIA_MAX) {
    return json({ ok: false, error: 'too_large', size: buf.length, max: MEDIA_MAX },
      413, corsFor(request, env, 'content'));
  }

  const raw = (form.get('name') && String(form.get('name'))) || file.name || 'file';
  const name = mediaSafeName(raw);
  const key = MEDIA_PREFIX + name;

  // ① R2
  await env.MEDIA.put(key, buf, {
    httpMetadata: { contentType: ctype },
    customMetadata: { uploaded_by: auth.uid, role: auth.role || '' }
  });

  // ② 同步落仓库 cms 分支（官网构建真源）。失败**不回滚 R2**——
  //    图已在媒体库可见，只是还没进仓库；前端把 gh 状态如实显示出来，不藏着。
  let gh = { ok: false, error: 'skipped' };
  try {
    const g = ghApi(env);
    const repoPath = 'assets/img/' + name;
    const cur = await fetch(g.base + '/contents/' + repoPath + '?ref=' + g.cms,
      { headers: g.headers, cf: { cacheTtl: 0 } });
    let sha = '';
    if (cur.ok) sha = (await cur.json()).sha;
    const payload = { message: 'media: upload ' + name, content: bytesToB64(buf), branch: g.cms };
    if (sha) payload.sha = sha;                 // 同名覆盖 = 换图（D105 证书墙就是这个玩法）
    const r = await fetch(g.base + '/contents/' + repoPath,
      { method: 'PUT', headers: g.headers, body: JSON.stringify(payload), cf: { cacheTtl: 0 } });
    gh = r.ok ? { ok: true, path: repoPath, overwritten: !!sha } : { ok: false, error: 'github_error', status: r.status };
  } catch (e) {
    gh = { ok: false, error: 'github_exception', detail: String(e && e.message).slice(0, 160) };
  }

  return json({
    ok: true, name, key, size: buf.length, type: ctype,
    url: '/media/file/' + key, gh
  }, 200, corsFor(request, env, 'content'));
}

// GET /media/file/<key> —— 免鉴权直读；R2 miss 则回源官网（仓库里已有的图）
async function handleMediaFile(request, env) {
  const url = new URL(request.url);
  const key = decodeURIComponent(url.pathname.slice('/media/file/'.length));
  if (!key.startsWith(MEDIA_PREFIX)) {
    return json({ ok: false, error: 'bad_key' }, 400, corsFor(request, env, 'content'));
  }

  if (env.MEDIA) {
    const o = await env.MEDIA.get(key);
    if (o) {
      const h = new Headers();
      h.set('Content-Type', (o.httpMetadata && o.httpMetadata.contentType) || 'application/octet-stream');
      h.set('Cache-Control', 'public, max-age=31536000, immutable');
      h.set('X-Media-Source', 'r2');
      return new Response(o.body, { status: 200, headers: h });
    }
  }
  // 回源：仓库 / 线上官网已有的图（CMS 分支还没合并的那些也能看）
  const up = await fetch(MEDIA_SITE + '/assets/' + key, { cf: { cacheTtl: 86400 } }).catch(() => null);
  if (!up || !up.ok) return json({ ok: false, error: 'not_found', key }, 404, corsFor(request, env, 'content'));
  const h = new Headers(up.headers);
  h.set('Cache-Control', 'public, max-age=3600');
  h.set('X-Media-Source', 'origin');
  return new Response(up.body, { status: 200, headers: h });
}

// DELETE /media/file/<key> —— 只删 R2（后台媒体库移除）
// ⚠️ 不同步删仓库：删仓库文件 = 改官网真源，风险高；要走发布流程由人确认。
async function handleMediaDelete(request, env) {
  const auth = await requireMember(request, env);
  if (!auth.ok) return json({ ok: false, error: auth.error }, 401, corsFor(request, env, 'content'));
  if (!env.MEDIA) return json({ ok: false, error: 'r2_not_bound' }, 503, corsFor(request, env, 'content'));

  const url = new URL(request.url);
  const key = decodeURIComponent(url.pathname.slice('/media/file/'.length));
  if (!key.startsWith(MEDIA_PREFIX)) {
    return json({ ok: false, error: 'bad_key' }, 400, corsFor(request, env, 'content'));
  }
  await env.MEDIA.delete(key);
  return json({ ok: true, deleted: key, note: '仅从后台媒体库移除；仓库里的同名文件需走发布流程处理' },
    200, corsFor(request, env, 'content'));
}
'''

assert s.count('\n// POST /publish') or True
s = s.rstrip('\n') + '\n' + MEDIA_FN
print('  ok 追加媒体库三个处理函数')

io.open(F, 'w', encoding='utf-8').write(s)
print('已写入', F, '大小', os.path.getsize(F))
