/**
 * ============================================================
 * VORLINA · 后台内容/发布路由（扩写模块 · 草稿 v20260920）
 * ============================================================
 * ⚠️ 本文件是「扩写源码」，**不要直接粘贴部署**。部署时粘贴同目录的
 *    `worker.merged.js`（已由构建脚本把本模块并入原 worker.js：替换路由块 + 追加 helper，
 *    并通过「无函数重名 / export default 唯一 / 三路由齐全」断言 + node --check）。
 *    本文件只用来审阅新增了什么（【ROUTER 替换块】在注释里，仅供阅读）。
 *
 * 复用现有 worker.js 里已定义的 helper：
 *   corsHeaders / json / isAllowedOrigin / supabaseEnv / safeEqual / allowRate
 * 本模块新增：corsFor / requireMember / handleContent / handleContentPut / handlePublish
 *
 * Secrets / env（在 CF Dashboard 或 wrangler 里配，绝不进仓库、绝不进浏览器）：
 *   GITHUB_TOKEN      fine-grained PAT，只授权 VorlinaSite 的 contents:write + actions:write
 *   GH_OWNER          orangesong-song
 *   GH_REPO           VorlinaSite
 *   GH_CMS_BRANCH     cms        （后台保存落这里）
 *   GH_MAIN_BRANCH    main       （只有 Actions 能写这里）
 *   GH_PUBLISH_WORKFLOW  publish.yml
 *
 * 权限闸门：所有 /content、/publish 请求都先过 requireMember（验 Supabase JWT + 查 members 表）。
 * 回滚仅 boss（方案 §权限）。其余角色发布不限。
 * ============================================================
 */

/* ──【ROUTER 替换块】把现有 worker.js 第 74–104 行整段替换为下面这个 ──────────────
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, '') || '/';
    const kind = path === '/content' ? 'content' : path === '/publish' ? 'publish' : 'enquiry';

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsFor(request, env, kind) });
    }

    // ③ 内容读写（私有仓库，必须经 Worker 持 token）
    if (path === '/content') {
      if (request.method === 'GET')  return handleContent(request, env);
      if (request.method === 'PUT')  return handleContentPut(request, env);
      return json({ ok: false, error: 'method_not_allowed' }, 405, corsFor(request, env, 'content'));
    }
    // ④ 发布（触发 Actions workflow_dispatch）
    if (path === '/publish') {
      if (request.method === 'POST') return handlePublish(request, env);
      return json({ ok: false, error: 'method_not_allowed' }, 405, corsFor(request, env, 'publish'));
    }

    if (request.method === 'GET') {
      if (path === '/enquiry' || path === '/probe') return probe(request, env);
      if (path === '/') {
        return json({
          ok: true, service: 'vorlina-inquiry',
          ready: {
            webhook: !!env.WEBHOOK_SECRET,
            recipient: !!env.NOTIFY_TO,
            smtp: !!(env.SMTP_USER && env.SMTP_PASS),
            content: !!env.GITHUB_TOKEN
          }
        }, 200);
      }
      return json({ ok: false, error: 'not_found' }, 404);
    }

    if (request.method !== 'POST') return json({ ok: false, error: 'method_not_allowed' }, 405);

    if (path === '/notify')  return handleNotify(request, env);
    if (path === '/enquiry') return handleEnquiry(request, env);
    return json({ ok: false, error: 'not_found' }, 404);
  }
};
────────────────────────────────────────────────────────────────────────────── */

function corsFor(request, env, kind) {
  const origin = request.headers.get('Origin') || '';
  const methods = kind === 'content' ? 'GET,PUT,OPTIONS'
    : kind === 'publish' ? 'POST,OPTIONS'
    : 'GET,OPTIONS';
  const h = {
    'Access-Control-Allow-Methods': methods,
    'Access-Control-Max-Age': '3600',
    'Cache-Control': 'no-store'
  };
  const allowHeaders = request.headers.get('Access-Control-Request-Headers') || 'content-type,authorization';
  if (origin && isAllowedOrigin(origin, env)) {
    h['Access-Control-Allow-Origin'] = origin;
    h['Vary'] = 'Origin';
    h['Access-Control-Allow-Headers'] = allowHeaders;
  } else {
    // 不在白名单也回头，让浏览器把真实状态码交给前端（避免变成 CORS 错误掩盖真 bug）
    h['Access-Control-Allow-Origin'] = origin || '*';
    h['Vary'] = 'Origin';
    h['Access-Control-Allow-Headers'] = allowHeaders;
  }
  return h;
}

// 验 Supabase JWT 身份 + 查 members 表确认是有效成员。返回 {ok, uid, role}
async function requireMember(request, env) {
  const auth = request.headers.get('Authorization') || '';
  const m = auth.match(/^Bearer\s+(.+)$/i);
  if (!m) return { ok: false, error: 'missing_token' };
  const jwt = m[1];
  const sb = supabaseEnv(env);

  // 1) 验 JWT 身份
  const u = await fetch(sb.url + '/auth/v1/user', {
    headers: { Authorization: 'Bearer ' + jwt, apikey: sb.key },
    cf: { cacheTtl: 0 }
  });
  if (u.status !== 200) return { ok: false, error: 'invalid_token' };
  const me = await u.json();
  if (!me.id) return { ok: false, error: 'invalid_token' };

  // 2) 查成员表（RLS: to authenticated using(true)，登录用户可读）
  const mem = await fetch(sb.url + '/rest/v1/members?select=id,role&auth_user_id=eq.' + encodeURIComponent(me.id), {
    headers: { apikey: sb.key, Authorization: 'Bearer ' + jwt },
    cf: { cacheTtl: 0 }
  });
  if (mem.status !== 200) return { ok: false, error: 'member_lookup_failed' };
  const rows = await mem.json();
  if (!Array.isArray(rows) || rows.length === 0) return { ok: false, error: 'not_member' };
  return { ok: true, uid: me.id, role: rows[0].role };
}

function ghApi(env) {
  return {
    owner: env.GH_OWNER || 'orangesong-song',
    repo: env.GH_REPO || 'VorlinaSite',
    cms: env.GH_CMS_BRANCH || 'cms',
    main: env.GH_MAIN_BRANCH || 'main',
    base: 'https://api.github.com/repos/' + (env.GH_OWNER || 'orangesong-song') + '/' + (env.GH_REPO || 'VorlinaSite'),
    headers: {
      Authorization: 'Bearer ' + env.GITHUB_TOKEN,
      Accept: 'application/vnd.github+json',
      'User-Agent': 'vorlina-admin',
      'Content-Type': 'application/json'
    }
  };
}

// GET /content?path=<repo相对路径>&ref=<分支，默认 cms>  → 与本地桩同形：{content(base64), sha, size}
async function handleContent(request, env) {
  const auth = await requireMember(request, env);
  if (!auth.ok) return json({ ok: false, error: auth.error }, 401, corsFor(request, env, 'content'));

  const url = new URL(request.url);
  const p = url.searchParams.get('path');
  const ref = url.searchParams.get('ref') || ghApi(env).cms;
  if (!p) return json({ ok: false, error: 'missing_path' }, 400, corsFor(request, env, 'content'));

  const g = ghApi(env);
  const r = await fetch(g.base + '/contents/' + p + '?ref=' + encodeURIComponent(ref), {
    headers: g.headers, cf: { cacheTtl: 0 }
  });
  if (r.status === 404) return json({ ok: false, error: 'not_found', path: p }, 404, corsFor(request, env, 'content'));
  if (!r.ok) return json({ ok: false, error: 'github_error', status: r.status }, r.status, corsFor(request, env, 'content'));
  const d = await r.json();
  return json({
    content: d.content, sha: d.sha, size: d.size,
    path: d.path, name: d.name
  }, 200, corsFor(request, env, 'content'));
}

// PUT /content  body: {path, message, content(base64), sha?}  → 提交到 cms 分支
async function handleContentPut(request, env) {
  const auth = await requireMember(request, env);
  if (!auth.ok) return json({ ok: false, error: auth.error }, 401, corsFor(request, env, 'content'));

  let body;
  try { body = await request.json(); } catch { return json({ ok: false, error: 'bad_json' }, 400, corsFor(request, env, 'content')); }
  const { path, message, content, sha } = body;
  if (!path || !content) return json({ ok: false, error: 'missing_fields' }, 400, corsFor(request, env, 'content'));

  const g = ghApi(env);
  const branch = g.cms;
  let curSha = sha;
  if (!curSha) {
    // 没传 sha → 先查当前（新文件则 GitHub 会创建，无需 sha）
    const cur = await fetch(g.base + '/contents/' + path + '?ref=' + branch, { headers: g.headers, cf: { cacheTtl: 0 } });
    if (cur.ok) curSha = (await cur.json()).sha;
  }
  const payload = { message: message || ('update ' + path), content, branch };
  if (curSha) payload.sha = curSha;

  const r = await fetch(g.base + '/contents/' + path, {
    method: 'PUT', headers: g.headers,
    body: JSON.stringify(payload)
  });
  if (!r.ok) {
    const detail = await r.text().catch(() => '');
    return json({ ok: false, error: 'github_put_failed', status: r.status, detail: detail.slice(0, 300) }, r.status, corsFor(request, env, 'content'));
  }
  const d = await r.json();
  return json({ ok: true, commit: d.commit && d.commit.sha, content_sha: d.content && d.content.sha, path }, 200, corsFor(request, env, 'content'));
}

// POST /publish  → 触发 Actions workflow_dispatch（merge cms→main + 升版本 + build）
async function handlePublish(request, env) {
  const auth = await requireMember(request, env);
  if (!auth.ok) return json({ ok: false, error: auth.error }, 401, corsFor(request, env, 'publish'));

  let body = {};
  try { body = await request.json(); } catch { body = {}; }

  // 回滚仅 boss（方案 §权限）。其余角色发布不限。
  if (body.action === 'rollback' && auth.role !== 'boss') {
    return json({ ok: false, error: 'role_denied', need: 'boss' }, 403, corsFor(request, env, 'publish'));
  }

  const g = ghApi(env);
  const wf = env.GH_PUBLISH_WORKFLOW || 'publish.yml';
  const r = await fetch(g.base + '/actions/workflows/' + wf + '/dispatches', {
    method: 'POST', headers: g.headers,
    body: JSON.stringify({ ref: g.main, inputs: { triggered_by: auth.uid, action: body.action || 'publish' } })
  });
  if (!r.ok) {
    const detail = await r.text().catch(() => '');
    return json({ ok: false, error: 'dispatch_failed', status: r.status, detail: detail.slice(0, 300) }, r.status, corsFor(request, env, 'publish'));
  }
  return json({ ok: true, dispatched: true, workflow: wf }, 202, corsFor(request, env, 'publish'));
}
