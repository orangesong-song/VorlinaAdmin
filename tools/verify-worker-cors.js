/**
 * vorlina-admin · Worker CORS 预检白名单单测（vadmin-019）
 * 2026-09-23 · 线上事故：/media/* 与 /changes 落进默认 kind → 'GET,OPTIONS' →
 *   浏览器预检拦死 POST 上传 / DELETE 移除 / POST 变更对比，页面只报「网络错误」。
 *
 * 为什么必须有这一层：**同源桩站不触发预检**，97 条浏览器断言全绿也照样漏。
 * 做法：把 worker.merged.js 复制到临时文件、追加一行 export，直接 import 出来打。
 * 断言口径 = 浏览器真正会看的那几个头（Allow-Methods 必须覆盖真实请求方法）。
 */
const fs = require('fs');
const path = require('path');
const os = require('os');

const SRC = process.env.WORKER_SRC || path.join(__dirname, '..', 'deploy', 'worker.merged.js');   /* WORKER_SRC 可指向旧副本，做「断言有没有牙齿」检验 */
const ORIGIN = 'https://admin.vorlina.net';
const PROD = { ALLOWED_ORIGINS: ORIGIN + ',https://vorlina.net,https://www.vorlina.net' };

let pass = 0, fail = 0;
const out = [];
function check(name, cond, detail) {
  if (cond) { pass++; out.push('  OK  ' + name); }
  else { fail++; out.push('  XX  ' + name + (detail ? '  -> ' + detail : '')); }
}
function section(t) { out.push('\n' + t); }

(async function main() {
  const tmp = path.join(os.tmpdir(), 'worker.cors-probe.' + process.pid + '.mjs');
  /* ⚠️ worker 里有 Cloudflare 专有 import（cloudflare:sockets，node 不认这个协议），
     离线跑单测时替换成桩 —— 只测 corsFor，不测 SMTP。 */
  const raw = fs.readFileSync(SRC, 'utf8');
  const stripped = raw.replace(/^import\s*\{[^}]*\}\s*from\s*["']cloudflare:[^"']+["'];?\s*$/m,
    'const connect = () => { throw new Error("cloudflare:sockets 桩 · 离线单测不涉及 SMTP") };');
  check('C0b 已剥离 Cloudflare 专有 import（否则 node 加载不了）', stripped !== raw);
  fs.writeFileSync(tmp, stripped + '\nexport { corsFor };\n');
  const mod = await import('file://' + tmp);
  const corsFor = mod.corsFor;
  check('C0 worker.merged.js 能作为 ES module 加载并导出 corsFor', typeof corsFor === 'function');

  /* 路由 → 真实必需的请求方法（与 worker 路由表逐条对齐） */
  const CASES = [
    ['/media/upload', 'POST', '后台选图弹层上传'],
    ['/media/file/img/x.png', 'DELETE', '媒体库移除'],
    ['/media/list', 'GET', '媒体列表'],
    ['/media/file/img/x.png', 'GET', '图片直读（免鉴权）'],
    ['/changes', 'POST', '变更对比'],
    ['/content', 'PUT', '保存草稿'],
    ['/publish', 'POST', '发布'],
    ['/enquiry', 'POST', '询盘提交'],
  ];

  section('C · 预检 Allow-Methods 必须覆盖该路由真实用到的方法');
  for (const [p, method, label] of CASES) {
    const req = new Request('https://notify.vorlina.net' + p, {
      method: 'OPTIONS',
      headers: {
        Origin: ORIGIN,
        'Access-Control-Request-Method': method,
        'Access-Control-Request-Headers': 'authorization,content-type',
      },
    });
    const h = corsFor(req, PROD, p === '/content' ? 'content' : p === '/publish' ? 'publish' : 'enquiry');
    const methods = h['Access-Control-Allow-Methods'] || '';
    check('C ' + method + ' ' + p + '（' + label + '）', methods.indexOf(method) >= 0, 'Allow-Methods = ' + methods);
  }

  section('C · 预检头本身不能缺项');
  const pre = new Request('https://notify.vorlina.net/media/upload', {
    method: 'OPTIONS',
    headers: {
      Origin: ORIGIN,
      'Access-Control-Request-Method': 'POST',
      'Access-Control-Request-Headers': 'authorization,content-type',
    },
  });
  const ph = corsFor(pre, PROD, 'enquiry');
  check('C9 白名单来源回显 Origin（预检才放行）', ph['Access-Control-Allow-Origin'] === ORIGIN, JSON.stringify(ph['Access-Control-Allow-Origin']));
  check('C10 Allow-Headers 回显请求头（authorization 必须在）', /authorization/i.test(ph['Access-Control-Allow-Headers'] || ''), ph['Access-Control-Allow-Headers']);
  check('C11 预检可缓存 + 不落 CDN（Max-Age 有值 / Cache-Control no-store）',
    !!ph['Access-Control-Max-Age'] && /no-store/.test(ph['Cache-Control'] || ''), JSON.stringify(ph['Cache-Control']));

  section('C · 非白名单来源也要回状态码（别把真错误伪装成 CORS 错误）');
  const evil = new Request('https://notify.vorlina.net/media/upload', {
    method: 'OPTIONS',
    headers: { Origin: 'https://evil.example', 'Access-Control-Request-Method': 'POST' },
  });
  const eh = corsFor(evil, PROD, 'enquiry');
  check('C12 陌生来源仍回 ACAO（走 401/405 真状态，而不是 CORS 报错）', !!eh['Access-Control-Allow-Origin'], JSON.stringify(eh['Access-Control-Allow-Origin']));

  try { fs.unlinkSync(tmp) } catch (e) {}
  console.log(out.join('\n'));
  console.log('\n' + '='.repeat(52));
  console.log('通过 ' + pass + ' / 失败 ' + fail);
  console.log('='.repeat(52));
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('单测自身出错：', e); process.exit(2) });
