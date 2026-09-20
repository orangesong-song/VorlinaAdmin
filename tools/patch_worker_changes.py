#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""worker.merged.js 补丁：requireMember 重试 + /changes + /commits 两个新路由。
每处替换前断言出现次数，写盘后 json 无关、node --check 另行验证。"""
import io, os, sys

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'deploy', 'worker.merged.js')
src = io.open(P, encoding='utf-8').read()
orig = src

def rep(old, new, n=1, tag=''):
    global src
    c = src.count(old)
    assert c == n, '断言失败 [%s]：%r 出现 %d 次（期望 %d）' % (tag, old[:60], c, n)
    src = src.replace(old, new)
    print('OK [%s]' % tag)

# ── 1. requireMember：members 查询失败重试一次 ─────────────────────
rep(
"""  // 2) 查成员表（RLS: to authenticated using(true)，登录用户可读）
  const mem = await fetch(sb.url + '/rest/v1/members?select=member_id,role&auth_user_id=eq.' + encodeURIComponent(me.id), {
    headers: { apikey: sb.key, Authorization: 'Bearer ' + jwt },
    cf: { cacheTtl: 0 }
  });
  if (mem.status !== 200) return { ok: false, error: 'member_lookup_failed' };""",
"""  // 2) 查成员表（RLS: to authenticated using(true)，登录用户可读）
  //    ⚠️ 偶发网络抖动在这里 5xx/超时 → 前端看到 401 member_lookup_failed
  //       （2026-09-20 总览 15 份并发读取 4 份误报实测）→ 失败自动重试一次。
  const memberUrl = sb.url + '/rest/v1/members?select=member_id,role&auth_user_id=eq.' + encodeURIComponent(me.id);
  const memberHeaders = { apikey: sb.key, Authorization: 'Bearer ' + jwt };
  let mem = await fetch(memberUrl, { headers: memberHeaders, cf: { cacheTtl: 0 } });
  if (mem.status !== 200) {
    await new Promise(r => setTimeout(r, 150));
    mem = await fetch(memberUrl, { headers: memberHeaders, cf: { cacheTtl: 0 } });
  }
  if (mem.status !== 200) return { ok: false, error: 'member_lookup_failed' };""",
1, 'retry')

# ── 2. 路由：/changes + /commits ──────────────────────────────────
rep(
"""    // ④ 发布（触发 Actions workflow_dispatch）
    if (path === '/publish') {""",
"""    // ④-2 变更对比（cms 草稿 vs main 线上，逐文件比 sha）
    if (path === '/changes') {
      if (request.method === 'POST') return handleChanges(request, env);
      return json({ ok: false, error: 'method_not_allowed' }, 405, corsFor(request, env, 'content'));
    }
    // ④-3 发布历史（main 最近提交）
    if (path === '/commits') {
      if (request.method === 'GET') return handleCommits(request, env);
      return json({ ok: false, error: 'method_not_allowed' }, 405, corsFor(request, env, 'content'));
    }
    // ⑤ 发布（触发 Actions workflow_dispatch）
    if (path === '/publish') {""",
1, 'routes')

# ── 3. 两个 handler 实现，追加在 handlePublish 之前 ────────────────
rep(
"""// POST /publish  → 触发 Actions workflow_dispatch（merge cms→main + 升版本 + build）
async function handlePublish(request, env) {""",
"""// POST /changes  body: {paths:[...]}  → 逐文件比 cms 与 main 的 blob sha
// 一次请求带回全部对比结果 —— 15 个文件逐个从前端问会把 requireMember 的 Supabase
// 查询放大 30 倍（2026-09-20 间歇 401 的教训），对比必须收敛在 Worker 一侧。
const PATH_RE = /^[A-Za-z0-9][A-Za-z0-9_\\-./%]*$/;
async function handleChanges(request, env) {
  const auth = await requireMember(request, env);
  if (!auth.ok) return json({ ok: false, error: auth.error }, 401, corsFor(request, env, 'content'));

  let body;
  try { body = await request.json(); } catch { body = {}; }
  const paths = (Array.isArray(body.paths) ? body.paths : []).filter(p => typeof p === 'string' && p.length < 200 && PATH_RE.test(p)).slice(0, 40);
  if (!paths.length) return json({ ok: false, error: 'missing_paths' }, 400, corsFor(request, env, 'content'));

  const g = ghApi(env);
  const files = await Promise.all(paths.map(async p => {
    const get = async ref => {
      const r = await fetch(g.base + '/contents/' + p + '?ref=' + encodeURIComponent(ref), { headers: g.headers, cf: { cacheTtl: 0 } });
      if (r.status === 404) return null;
      if (!r.ok) throw new Error('github ' + r.status + ' ' + p);
      const d = await r.json();
      return { sha: d.sha, size: d.size };
    };
    try {
      const [m, c] = await Promise.all([get(g.main), get(g.cms)]);
      return { path: p, main: m, cms: c, changed: !m || !c ? true : m.sha !== c.sha };
    } catch (e) {
      return { path: p, error: String(e.message || e).slice(0, 120) };
    }
  }));
  return json({ ok: true, files }, 200, corsFor(request, env, 'content'));
}

// GET /commits?per=12  → main 最近提交（发布历史页）
async function handleCommits(request, env) {
  const auth = await requireMember(request, env);
  if (!auth.ok) return json({ ok: false, error: auth.error }, 401, corsFor(request, env, 'content'));

  const url = new URL(request.url);
  const per = Math.min(Math.max(parseInt(url.searchParams.get('per') || '12', 10) || 12, 1), 30);
  const g = ghApi(env);
  const r = await fetch(g.base + '/commits?sha=' + g.main + '&per_page=' + per, { headers: g.headers, cf: { cacheTtl: 0 } });
  if (!r.ok) {
    const detail = await r.text().catch(() => '');
    return json({ ok: false, error: 'github_error', status: r.status, detail: detail.slice(0, 200) }, r.status, corsFor(request, env, 'content'));
  }
  const list = await r.json();
  return json({
    ok: true,
    commits: (Array.isArray(list) ? list : []).map(c => ({
      sha: (c.sha || '').slice(0, 7),
      date: c.commit && c.commit.author && c.commit.author.date || '',
      message: ((c.commit && c.commit.message) || '').split('\\n')[0].slice(0, 120),
      author: (c.commit && c.commit.author && c.commit.author.name) || (c.author && c.author.login) || '-'
    }))
  }, 200, corsFor(request, env, 'content'));
}

// POST /publish  → 触发 Actions workflow_dispatch（merge cms→main + 升版本 + build）
async function handlePublish(request, env) {""",
1, 'handlers')

assert src != orig
io.open(P, 'w', encoding='utf-8').write(src)
print('补丁完成 →', P)
