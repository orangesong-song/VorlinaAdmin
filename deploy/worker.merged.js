/**
 * ============================================================
 * VORLINA · 询盘 Worker（一个 Worker 干三件事）
 * ============================================================
 * ① GET  /enquiry    就绪探针（给官网前端用）
 * ② POST /enquiry    代写通道：买家的浏览器连不上 Supabase 时，把询盘交给它代写
 * ③ POST /notify     收到 Supabase 的 INSERT 通知 → 发邮件给 info@vorlina.net
 *
 * 为什么需要 ②：部分网络（本机代理改坏 TLS、公司防火墙、区域网络）
 * 到不了 *.supabase.co。官网前端会先直连，失败才改走这里 ——
 * 这样买家/同事不需要改任何网络配置。
 *
 * ── 路由与鉴权 ───────────────────────────────────────────────
 *   GET  /            健康检查（只看配置齐不齐，不泄露密钥）
 *   GET  /enquiry     探针：本 Worker 能否连上 Supabase
 *   POST /enquiry     公开（带 CORS），靠来源白名单 + 蜜罐 + 限频 + 数据库约束兜底
 *   POST /notify      需要 x-webhook-secret 与 Supabase Webhook 里那串一致
 *
 * ── Cloudflare 环境变量 / Secrets ─────────────────────────────
 *   WEBHOOK_SECRET   与 Supabase Webhook 的 x-webhook-secret 一致（必填）
 *   NOTIFY_TO        收件人，如 info@vorlina.net（必填）
 *   SMTP_USER        企业邮箱完整地址（必填）
 *   SMTP_PASS        企业邮箱密码 / 客户端专用密码（必填）
 *   SMTP_HOST        可选，默认 smtp.qiye.aliyun.com
 *   SMTP_FROM        可选，默认取 SMTP_USER。
 *                    ⚠️ 想让**通知邮件本身**也来自 vorlina.net（同事就不会搞混身份），
 *                       填 info@vorlina.net —— 但**必须先在 vorlina.net 的 DNS 里补上 SPF**：
 *                       TXT  @  =  v=spf1 include:spf.qiye.aliyun.com -all
 *                       没有 SPF 就发信，收件方查不到出站授权，很容易进垃圾箱。
 *   SMTP_FROM_NAME   可选，默认 "VORLINA website"
 *   SUPABASE_URL     可选，默认见下方（项目地址是公开信息）
 *   SUPABASE_ANON    可选，默认见下方（anon key 本就是公开密钥）
 *   ALLOWED_ORIGINS  可选，逗号分隔；默认允许官网域名 + 本地调试
 *
 * ⚠️ 代写通道用的是 **anon key**（不是 service_role）——
 *    权限与浏览器直连时完全一样，数据库 RLS 照常收口，
 *    所以这个公开端点即使被刷，也造不出"已成交/已归属"的假记录。
 * ============================================================
 */
import { connect } from "cloudflare:sockets";

const DEFAULT_SUPABASE_URL = 'https://jjmaularjtmhptbfnovd.supabase.co';
const DEFAULT_SUPABASE_ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpqbWF1bGFyanRtaHB0YmZub3ZkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODg3ODYwMTgsImV4cCI6MjEwNDM2MjAxOH0.t5RJfF34qfiBQZaqAcp3NnCOxo_38okIAzSrJNspSrI';
const DEFAULT_ORIGINS = [
  'https://b01e7caab80e4c1497a27c06cc4e5608.app.workbuddy.host',
  'https://vorlina.net',
  'https://www.vorlina.net'
];

const SMTP_PORT = 465;
const SMTP_TIMEOUT_MS = 15000;
const MAX_BODY_BYTES = 256 * 1024;

// 限频（实例内存级，够用；真要硬防刷再上 Cloudflare Rate Limiting / WAF）
const RL_WINDOW_MS = 10 * 60 * 1000;
const RL_PER_IP = 6;
const RL_GLOBAL = 200;
const rlIp = new Map();
let rlGlobal = { start: 0, count: 0 };

/** 允许写入的字段白名单（与库表一致；status/owner_id/internal_note 一律不接受） */
const FIELDS = [
  'name', 'company', 'email', 'country', 'phone',
  'models', 'models_note', 'message',
  'source', 'page_url', 'referrer', 'user_agent', 'timezone',
  'fill_ms', 'consent', 'consent_at', 'client_ref'
];
const LIMITS = {
  name: 200, company: 200, email: 320, country: 100, phone: 50,
  models_note: 500, message: 5000, source: 40, page_url: 500,
  referrer: 500, user_agent: 500, timezone: 60, client_ref: 40
};

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
    // ④-2 变更对比（cms 草稿 vs main 线上，逐文件比 sha）
    if (path === '/changes') {
      if (request.method === 'POST') return handleChanges(request, env);
      return json({ ok: false, error: 'method_not_allowed' }, 405, corsFor(request, env, 'content'));
    }
    // ④-3 发布历史（main 最近提交）
    if (path === '/commits') {
      if (request.method === 'GET') return handleCommits(request, env);
      return json({ ok: false, error: 'method_not_allowed' }, 405, corsFor(request, env, 'content'));
    }
    // ⑥ 媒体库（R2 直传 · 后台运营上传图片 / 目录 PDF）
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


/* ============================================================
   ① 探针：前端用它判断"后端就绪了没"
   ============================================================ */
async function probe(request, env) {
  const sb = supabaseEnv(env);
  const headers = corsHeaders(request, env, 'enquiry');
  try {
    const r = await fetch(sb.url + '/rest/v1/inquiries?select=id&limit=1', {
      headers: { 'apikey': sb.key, 'Authorization': 'Bearer ' + sb.key },
      cf: { cacheTtl: 0 }
    });
    // 200 + [] = 表在（anon 无 SELECT 策略，永远读不到行）；404 = 表还没建
    return json({ ok: true, ready: r.status === 200 }, 200, headers);
  } catch (e) {
    return json({ ok: false, ready: false, error: 'upstream_unreachable' }, 200, headers);
  }
}

/* ============================================================
   ② 代写：前端直连失败时的备援通道
   ============================================================ */
async function handleEnquiry(request, env) {
  const headers = corsHeaders(request, env, 'enquiry');
  const origin = request.headers.get('Origin') || '';

  if (origin && !isAllowedOrigin(origin, env)) {
    return json({ ok: false, error: 'origin_not_allowed' }, 403, headers);
  }

  const len = Number(request.headers.get('content-length') || 0);
  if (len > MAX_BODY_BYTES) return json({ ok: false, error: 'body_too_large' }, 413, headers);

  let body;
  try { body = JSON.parse(await request.text()); }
  catch (e) { return json({ ok: false, error: 'invalid_json' }, 400, headers); }
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return json({ ok: false, error: 'invalid_payload' }, 400, headers);
  }

  // 蜜罐：与前端同一套。命中就假装成功，什么都不做。
  if (body.company_website) return json({ ok: true, honeypot: true }, 200, headers);

  const ip = request.headers.get('cf-connecting-ip') || 'unknown';
  if (!allowRate(ip)) {
    console.log(JSON.stringify({ evt: 'enquiry_rate_limited', ip: ip.slice(0, 24) }));
    return json({ ok: false, error: 'rate_limited' }, 429, headers);
  }

  // 白名单 + 截断（数据库那边还有一层 CHECK，这里先挡一遍好给出清楚的报错）
  const row = {};
  for (const k of FIELDS) {
    if (!(k in body)) continue;
    let v = body[k];
    if (k === 'models') {
      row.models = Array.isArray(v) ? v.slice(0, 50).map(x => String(x).slice(0, 60)) : [];
      continue;
    }
    if (k === 'fill_ms') { const n = Number(v); row.fill_ms = Number.isFinite(n) ? Math.max(0, Math.min(86400000, Math.round(n))) : null; continue; }
    if (k === 'consent') { row.consent = v === true; continue; }
    if (v === null || v === undefined) { row[k] = null; continue; }
    row[k] = String(v).slice(0, LIMITS[k] || 500);
  }
  row.via = 'worker-fallback';           // 强制标记来路，不接受前端自报

  if (!row.name || !row.company || !row.email) {
    return json({ ok: false, error: 'missing_required_fields' }, 400, headers);
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(row.email)) {
    return json({ ok: false, error: 'invalid_email' }, 400, headers);
  }
  row.consent = row.consent === true;
  if (!row.consent_at) row.consent_at = new Date().toISOString();

  const sb = supabaseEnv(env);
  try {
    const r = await fetch(sb.url + '/rest/v1/inquiries', {
      method: 'POST',
      headers: {
        'apikey': sb.key,
        'Authorization': 'Bearer ' + sb.key,
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'          // 少了这个，PostgREST 会试图回传插入行 → 撞 anon 没有的 SELECT 权限
      },
      body: JSON.stringify(row)
    });

    if (r.status === 201 || r.status === 200) {
      console.log(JSON.stringify({ evt: 'enquiry_saved', via: 'worker', company: row.company.slice(0, 50) }));
      return json({ ok: true }, 200, headers);
    }
    if (r.status === 409) {
      // client_ref 唯一索引拦下的重复投递 —— 对前端而言就是"已经存进去了"
      console.log(JSON.stringify({ evt: 'enquiry_duplicate', client_ref: String(row.client_ref || '').slice(0, 40) }));
      return json({ ok: true, duplicate: true }, 200, headers);
    }
    const detail = (await r.text()).slice(0, 200);
    console.log(JSON.stringify({ evt: 'enquiry_write_failed', status: r.status, detail: detail }));
    return json({ ok: false, error: 'write_rejected', detail: detail }, r.status >= 500 ? 502 : 400, headers);
  } catch (e) {
    const detail = String((e && e.message) || e).slice(0, 160);
    console.log(JSON.stringify({ evt: 'enquiry_write_error', error: detail }));
    return json({ ok: false, error: 'upstream_unreachable', detail: detail }, 502, headers);
  }
}

/* ============================================================
   ③ 通知：Supabase Database Webhook → 发邮件
   ============================================================ */
async function handleNotify(request, env) {
  const secret = env.WEBHOOK_SECRET || '';
  const got = request.headers.get('x-webhook-secret') || '';
  if (!secret) return json({ ok: false, error: 'worker_not_configured' }, 503);
  if (!safeEqual(got, secret)) {
    console.log(JSON.stringify({ evt: 'notify_unauthorized' }));
    return json({ ok: false, error: 'unauthorized' }, 401);
  }

  const len = Number(request.headers.get('content-length') || 0);
  if (len > MAX_BODY_BYTES) return json({ ok: false, error: 'body_too_large' }, 413);

  let payload;
  try { payload = JSON.parse(await request.text()); }
  catch (e) { return json({ ok: false, error: 'invalid_json' }, 400); }

  const record = payload && typeof payload.record === 'object' && payload.record ? payload.record : null;
  if (!record) return json({ ok: true, skipped: 'no_record' }, 200);
  if (payload.table && payload.table !== 'inquiries') return json({ ok: true, skipped: 'other_table' }, 200);
  if (payload.type && payload.type !== 'INSERT') return json({ ok: true, skipped: payload.type }, 200);

  const to = (env.NOTIFY_TO || '').trim();
  const user = env.SMTP_USER || '';
  const pass = env.SMTP_PASS || '';
  if (!to || !user || !pass) {
    console.log(JSON.stringify({ evt: 'notify_smtp_not_configured' }));
    return json({ ok: false, error: 'smtp_not_configured' }, 503);
  }
  if (!allowRate('notify:' + (request.headers.get('cf-connecting-ip') || 'x'))) {
    return json({ ok: false, error: 'rate_limited' }, 429);
  }

  const mail = buildMail(record);
  const host = env.SMTP_HOST || 'smtp.qiye.aliyun.com';
  const wantedFrom = env.SMTP_FROM || user;
  const fromName = env.SMTP_FROM_NAME || 'VORLINA website';
  // 兜底开关：设成 'off' 就严格按 SMTP_FROM 发、失败即失败（不做降级）
  const allowFallback = String(env.SMTP_FROM_FALLBACK || '').toLowerCase() !== 'off';

  const attempt = (from, body) => smtpSend({
    host: host, port: SMTP_PORT, user: user, pass: pass,
    from: from, fromName: fromName, to: to,
    replyTo: mail.replyTo, subject: mail.subject, body: body,
    messageId: "<inquiry." + crypto.randomUUID() + "@" + (from.split("@")[1] || "localhost") + ">"
  });

  try {
    let degradedFrom = null;
    try {
      await attempt(wantedFrom, mail.body);
    } catch (e) {
      const msg = String((e && e.message) || e);
      // 服务商说「这个发件地址没被当前登录账号授权」时，退一步用登录账号本身发信。
      // 宁可让同事看到母公司域的发件人，也不能让一条询盘通知凭空消失。
      // 注意：邮件正文里会写明原因，所以这不是"悄悄降级"。
      if (allowFallback && wantedFrom !== user && FROM_NOT_AUTHORISED.test(msg)) {
        degradedFrom = wantedFrom;
        // ⚠️ 一定要把说明插进正文 —— 否则就是"悄悄换了发件人身份"，
        //    同事不会知道该用哪个身份回复（这正是 D109 要防的事）。
        await attempt(user, mail.body + degradedNotice(wantedFrom, user));
      } else {
        throw e;
      }
    }

    console.log(JSON.stringify({
      evt: degradedFrom ? 'inquiry_notified_ok_from_fallback' : 'inquiry_notified_ok',
      to: to,
      sent_as: degradedFrom ? user : wantedFrom,
      wanted_from: degradedFrom || undefined,
      inquiry_id: String(record.id || "").slice(0, 40),
      via: String(record.via || "direct").slice(0, 20),
      company: String(record.company || "").slice(0, 60)
    }));
    if (degradedFrom) {
      console.log(JSON.stringify({
        evt: 'smtp_from_not_authorised',
        hint: 'SMTP_USER/SMTP_PASS 换成 ' + degradedFrom + ' 自己的账号，或把它加成当前账号的别名',
        wanted_from: degradedFrom, sent_as: user
      }));
    }
    return json({
      ok: true, sent: true,
      sent_as: degradedFrom ? user : wantedFrom,
      degraded_from: degradedFrom || undefined
    }, 200);
  } catch (e) {
    const detail = String((e && e.message) || e).slice(0, 200);
    console.log(JSON.stringify({ evt: 'inquiry_notify_failed', error: detail }));
    return json({ ok: false, error: 'smtp_send_failed', detail: detail }, 502);
  }
}

/* 服务商拒绝以某个地址发信时，各家措辞不同：
   阿里云企业邮  → "SMTP 440 mail from account doesn't conform with authentication"
   通用 SMTP     → "553 Mail from must equal authorized user"
   —— 认「两个账号不一致」这个语义，别只匹配某一个数字码。 */
const FROM_NOT_AUTHORISED =
  /conform with authentication|must equal authorized user|mail from.*(rejected|denied|not allowed|not permitted)|sender( address)? (rejected|denied)/i;

/* 降级发信时插进正文的说明 —— 让同事知道发件人为什么不是 vorlina.net */
function degradedNotice(wanted, used) {
  return "\n\n============================================================\n" +
         "⚠ THIS NOTIFICATION WAS SENT AS " + used + "\n" +
         "  The mail server refused \"" + wanted + "\" because it is not\n" +
         "  authorised for the account we sign in with.\n" +
         "  Fix it properly: either sign in with the " + wanted + " account\n" +
         "  (SMTP_USER / SMTP_PASS), or add it as an alias of the current\n" +
         "  account. The buyer never sees any of this — it only affects\n" +
         "  which identity you reply from.\n" +
         "============================================================\n";
}

/* ============================================================
   邮件内容
   ============================================================ */
function buildMail(r) {
  const s = v => (v === null || v === undefined ? "" : String(v));
  const one = v => s(v).replace(/[\r\n]+/g, " ").trim();      // 表头里绝不能出现换行

  const name = one(r.name);
  const company = one(r.company) || "Unknown company";
  const email = one(r.email);
  const country = one(r.country);
  const phone = one(r.phone);
  const models = Array.isArray(r.models) ? r.models.slice(0, 50).map(x => one(x)).filter(Boolean) : [];
  const modelsNote = one(r.models_note);
  const source = one(r.source) || "website";
  const via = one(r.via) || "direct";
  const pageUrl = one(r.page_url);
  const tzName = one(r.timezone);
  const fillMs = Number(r.fill_ms);
  const createdAt = one(r.created_at);

  const modelLine = models.length ? models.join(", ") : "(none selected)";

  /* 主题里必须带**能把两封邮件区分开**的东西：
     只写「公司 + 国家 + 型号数」的话，同一家公司连发两笔询盘（或连着测试两次）
     两封邮件的主题会一模一样，收件人根本分不清是不是重复投递 —— 我们就被这个坑过一次。
     所以：带上访客姓名，末尾再缀 8 位询盘号。
     ⚠️ 编号取 client_ref（前端生成）前 8 位 —— 官网提交成功后，成功卡片上给客户看的
     就是这个号，两边必须同源同格式，否则客户报出编号、你在邮件里查不到。
     （原实现用的是数据库 id 前 8 位，客户根本看不到，等于白给。）
     client_ref 为空时（手工补录的询盘）退回用 id，保证主题里始终有编号。 */
  const inqRef = (one(r.client_ref) || one(r.id)).replace(/-/g, "").slice(0, 8).toUpperCase();
  const who = [name, company].filter(function (x) { return x; }).join(" · ");
  const subject = "[VORLINA] New enquiry — " + (who || "Unknown")
    + (country ? " (" + country + ")" : "")
    + (models.length ? " · " + models.length + " model" + (models.length > 1 ? "s" : "") : "")
    + (inqRef ? " · #" + inqRef : "");

  const fillTxt = Number.isFinite(fillMs) && fillMs > 0
    ? (fillMs / 1000).toFixed(1) + " s" + (fillMs < 1500 ? "  ← 可疑：快得像脚本" : "")
    : "—";

  const lines = [
    "NEW WEBSITE ENQUIRY",
    "===================",
    "",
    "Received  : " + (createdAt || new Date().toISOString()),
    "Source    : " + source + (pageUrl ? "  (" + pageUrl + ")" : ""),
    "Route     : " + via + (via === "worker-fallback"
      ? "  ← 买家网络到不了数据库，走了代写通道" : ""),
    "",
    "BUYER",
    "-----",
    "Name      : " + (name || "—"),
    "Company   : " + (company || "—"),
    "Email     : " + (email || "—"),
    "Country   : " + (country || "—"),
    "Phone/WA  : " + (phone || "—"),
    "Timezone  : " + (tzName || "—"),
    "",
    "WHAT THEY ASKED FOR",
    "-------------------",
    "Models    : " + modelLine,
  ];
  if (modelsNote) lines.push("Typed refs: " + modelsNote);
  lines.push(
    "",
    "Message",
    "-------",
    s(r.message).trim() || "(no message)",
    "",
    "----",
    "Reply directly to this email — it goes straight back to the buyer.",
    "",
    "⚠ Use your info@vorlina.net identity to reply.",
    "  Whatever account you reply FROM is the address the buyer will see —",
    "  replying from an @hipdeer.com account shows them hipdeer.com, not VORLINA.",
    "",
    "Fill time : " + fillTxt,
    "Buyer ref : #" + inqRef + "   ← 客户在网站成功页上看到的编号，他回信报的就是这个",
    "Enquiry id: " + (one(r.id) || "—"),
    "",
    "Open the inquiry list in your work centre to assign it or mark it quoted."
  );

  return {
    subject: subject,
    body: lines.join("\n"),
    replyTo: /^[^\s@<>;,]+@[^\s@<>;,]+\.[^\s@<>;,]+$/.test(email) ? email : ""
  };
}

/* ============================================================
   杂项
   ============================================================ */
function supabaseEnv(env) {
  return {
    url: (env.SUPABASE_URL || DEFAULT_SUPABASE_URL).replace(/\/+$/, ''),
    key: env.SUPABASE_ANON || DEFAULT_SUPABASE_ANON
  };
}

function allowedOrigins(env) {
  const raw = (env.ALLOWED_ORIGINS || '').trim();
  if (!raw) return DEFAULT_ORIGINS;
  return raw.split(',').map(x => x.trim()).filter(Boolean);
}

function isAllowedOrigin(origin, env) {
  if (allowedOrigins(env).includes(origin)) return true;
  // 本地调试放行（localhost 来源不可能被远端网页伪造）
  return /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
}

function corsHeaders(request, env, kind) {
  const origin = request.headers.get('Origin') || '';
  const h = {
    'Access-Control-Allow-Methods': kind === 'enquiry' ? 'GET,POST,OPTIONS' : 'GET,OPTIONS',
    'Access-Control-Max-Age': '3600',
    'Cache-Control': 'no-store'
  };
  if (origin && isAllowedOrigin(origin, env)) {
    h['Access-Control-Allow-Origin'] = origin;
    h['Vary'] = 'Origin';
    h['Access-Control-Allow-Headers'] = request.headers.get('Access-Control-Request-Headers')
      || 'content-type';
  } else {
    // 不在白名单时也回一个头，好让浏览器把真实的状态码/报错交给前端（而不是变成 CORS 错误）
    h['Access-Control-Allow-Origin'] = origin || '*';
    h['Vary'] = 'Origin';
    h['Access-Control-Allow-Headers'] = request.headers.get('Access-Control-Request-Headers') || 'content-type';
  }
  return h;
}

function json(obj, status, extraHeaders) {
  return new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: Object.assign({
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store'
    }, extraHeaders || {})
  });
}

function safeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function allowRate(key) {
  const now = Date.now();
  if (now - rlGlobal.start >= RL_WINDOW_MS) { rlGlobal = { start: now, count: 0 }; }
  rlGlobal.count += 1;
  if (rlGlobal.count > RL_GLOBAL) return false;

  const old = rlIp.get(key) || { start: now, count: 0 };
  if (now - old.start >= RL_WINDOW_MS) { old.start = now; old.count = 0; }
  old.count += 1;
  rlIp.set(key, old);
  if (rlIp.size > 5000) {
    for (const [k, v] of rlIp) if (now - v.start >= RL_WINDOW_MS) rlIp.delete(k);
  }
  return old.count <= RL_PER_IP;
}

function b64(value) {
  const bytes = new TextEncoder().encode(String(value));
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

function headerEncode(value) {
  return /[^\x20-\x7E]/.test(value) ? "=?UTF-8?B?" + b64(value) + "?=" : value;
}

function smtpMessage(input) {
  const lines = [
    "From: " + (input.fromName ? headerEncode(input.fromName) + " <" + input.from + ">" : input.from),
    "To: " + input.to
  ];
  if (input.replyTo) lines.push("Reply-To: " + input.replyTo);
  lines.push(
    "Subject: " + headerEncode(input.subject),
    "Date: " + new Date().toUTCString(),
    "Message-ID: " + input.messageId,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=UTF-8",
    "Content-Transfer-Encoding: base64",
    "Auto-Submitted: auto-generated",
    "",
    (b64(input.body).match(/.{1,76}/g) || []).join("\r\n")
  );
  return lines.join("\r\n") + "\r\n.\r\n";
}

async function smtpSend(input) {
  const socket = connect({ hostname: input.host, port: input.port },
    { secureTransport: "on", allowHalfOpen: true });
  await socket.opened;
  const reader = socket.readable.getReader();
  const writer = socket.writable.getWriter();
  let buffer = "";

  async function readResponse() {
    const deadline = Date.now() + SMTP_TIMEOUT_MS;
    while (Date.now() < deadline) {
      const match = buffer.match(/^(\d{3})([ -])(.*?)(?:\r?\n|$)/);
      if (match && match[0].endsWith("\n")) {
        buffer = buffer.slice(match[0].length);
        if (match[2] === "-") continue;                       // 多行响应，继续读
        if (match[1][0] !== "2" && match[1][0] !== "3") throw new Error("SMTP " + match[1] + " " + match[3]);
        return match[1];
      }
      const next = await Promise.race([
        reader.read(),
        new Promise(function (_, reject) {
          setTimeout(function () { reject(new Error("SMTP response timeout")); }, SMTP_TIMEOUT_MS);
        })
      ]);
      if (next.done) throw new Error("SMTP connection closed");
      buffer += new TextDecoder().decode(next.value);
    }
    throw new Error("SMTP response timeout");
  }

  async function write(command) {
    await writer.write(new TextEncoder().encode(command + "\r\n"));
    return readResponse();
  }

  try {
    await readResponse();                                     // 服务端问候
    await write("EHLO vorlina-inquiry");
    await write("AUTH LOGIN");
    await write(b64(input.user));
    await write(b64(input.pass));
    await write("MAIL FROM:<" + input.from + ">");
    for (const recipient of input.to.split(",")) {
      const r = recipient.trim();
      if (r) await write("RCPT TO:<" + r + ">");
    }
    await write("DATA");
    await writer.write(new TextEncoder().encode(smtpMessage(input)));
    await readResponse();
    await write("QUIT");
  } finally {
    try { reader.releaseLock(); } catch (e) {}
    try { writer.releaseLock(); } catch (e) {}
    try { await socket.close(); } catch (e) {}
  }
}

/* ============================================================
   以下为后台内容/发布路由的新增 helper（v20260920 扩写模块并入）
   corsFor / requireMember / ghApi / handleContent / handleContentPut / handlePublish
   ============================================================ */

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
  //    ⚠️ 偶发网络抖动在这里 5xx/超时 → 前端看到 401 member_lookup_failed
  //       （2026-09-20 总览 15 份并发读取 4 份误报实测）→ 失败自动重试一次。
  const memberUrl = sb.url + '/rest/v1/members?select=member_id,role&auth_user_id=eq.' + encodeURIComponent(me.id);
  const memberHeaders = { apikey: sb.key, Authorization: 'Bearer ' + jwt };
  let mem = await fetch(memberUrl, { headers: memberHeaders, cf: { cacheTtl: 0 } });
  if (mem.status !== 200) {
    await new Promise(r => setTimeout(r, 150));
    mem = await fetch(memberUrl, { headers: memberHeaders, cf: { cacheTtl: 0 } });
  }
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

// POST /changes  body: {paths:[...]}  → 逐文件比 cms 与 main 的 blob sha
// 一次请求带回全部对比结果 —— 15 个文件逐个从前端问会把 requireMember 的 Supabase
// 查询放大 30 倍（2026-09-20 间歇 401 的教训），对比必须收敛在 Worker 一侧。
const PATH_RE = /^[A-Za-z0-9][A-Za-z0-9_\-./%]*$/;
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
      message: ((c.commit && c.commit.message) || '').split('\n')[0].slice(0, 120),
      author: (c.commit && c.commit.author && c.commit.author.name) || (c.author && c.author.login) || '-'
    }))
  }, 200, corsFor(request, env, 'content'));
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
