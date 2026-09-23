/**
 * vorlina-admin · P1 第 1 步「真实登录 + 成员校验」真实浏览器验证
 * 2026-09-20 · 无头 Chrome（puppeteer-core）
 *
 * 为什么必须 mock：
 *   真登录需要真实账号密码，且**验证的重点恰恰是失败路径**（密码错 / 非成员 / 令牌过期），
 *   这些都不该拿真实账号去试。所以把 Supabase 的四个端点做成可切换场景的假服务。
 *
 * ⚠️ 已知坑：mock 响应**必须自带 CORS 头（含 OPTIONS 预检）**，
 *    否则浏览器把请求判为 CORS 失败，看起来像「站点坏了」—— 实际是夹具的问题。
 */
const path = require('path');
const puppeteer = require('puppeteer-core');

const SB = 'https://jjmaularjtmhptbfnovd.supabase.co';
const ORIGIN = 'http://127.0.0.1:8778';
const URL_PAGE = ORIGIN + '/index.html';
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

let pass = 0, fail = 0;
const results = [];
function check(name, cond, detail) {
  if (cond) { pass++; results.push('  ✓ ' + name); }
  else { fail++; results.push('  ✗ ' + name + (detail ? '  → ' + detail : '')); }
}

/* 场景：测试过程中按需改这些值 */
const S = {
  signin: 'ok',        // ok | badcreds
  token: 'ok',         // ok(200) | old(401) —— /auth/v1/user
  member: 'staff',     // staff | boss | none(非成员) | empty
  refresh: 'ok',       // ok | fail
  refreshed: false,    // ⚠️ 关键：续期成功后 /auth/v1/user 必须转为 200，否则重试必然失败（夹具自己的 bug）
  calls: [],
};
function memberRow() {
  if (S.member === 'none') return [];
  return [{ member_id: 'M002', name: S.member === 'boss' ? '宋宋' : '林晓',
            role: S.member === 'boss' ? 'boss' : '业务员', email: 'ops@vorlina.net' }];
}

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--window-size=1440,900'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  const jsErrors = [];
  page.on('pageerror', e => jsErrors.push(String(e.message)));
  /* ⚠️ 夹具故意让 signin/refresh 返回 400 —— 浏览器会记 'Failed to load resource'。
     那是**网络状态码**不是 JS 异常，必须排除，否则断言永远红。
     JS 异常一律走 pageerror（未捕获异常与未处理的 promise rejection 都会到这）。 */
  const netNoise = [];
  page.on('console', m => {
    if (m.type() !== 'error') return;
    if (/Failed to load resource/.test(m.text())) netNoise.push(m.text());
    else jsErrors.push('console: ' + m.text());
  });

  await page.setRequestInterception(true);
  page.on('request', req => {
    const url = req.url();
    if (!url.startsWith(SB)) return req.continue();
    const cors = {
      'Access-Control-Allow-Origin': ORIGIN,
      'Access-Control-Allow-Headers': req.headers()['access-control-request-headers'] || '*',
      'Access-Control-Allow-Methods': 'GET,POST,PATCH,DELETE,OPTIONS',
    };
    const body = (o, status) => req.respond({ status: status || 200, contentType: 'application/json',
                                              headers: cors, body: JSON.stringify(o) });
    if (req.method() === 'OPTIONS') return req.respond({ status: 204, headers: cors, body: '' });

    S.calls.push(req.method() + ' ' + url.replace(SB, ''));

    if (url.includes('/auth/v1/token?grant_type=password')) {
      if (S.signin === 'badcreds') return body({ error: 'invalid_grant', error_description: 'Invalid login credentials' }, 400);
      return body({ access_token: 'AT-1', refresh_token: 'RT-1', expires_in: 3600,
                    user: { id: 'uid-1', email: 'ops@vorlina.net' } });
    }
    if (url.includes('/auth/v1/token?grant_type=refresh_token')) {
      if (S.refresh === 'fail') return body({ error: 'invalid_grant', error_description: 'Invalid Refresh Token' }, 400);
      S.refreshed = true;
      return body({ access_token: 'AT-2', refresh_token: 'RT-2', expires_in: 3600,
                    user: { id: 'uid-1', email: 'ops@vorlina.net' } });
    }
    if (url.includes('/auth/v1/user')) {
      if (S.token === 'old' && !S.refreshed) return body({ message: 'JWT expired' }, 401);
      return body({ id: 'uid-1', email: 'ops@vorlina.net' });
    }
    if (url.includes('/rest/v1/members')) return body(memberRow());
    return body({});
  });

  const state = () => page.evaluate(() => ({
    loginHidden: document.getElementById('login').hidden,
    appHidden: document.getElementById('app').hidden,
    who: (document.getElementById('whoName') || {}).textContent,
    role: (document.getElementById('whoRole') || {}).textContent,
    msg: (document.getElementById('loginMsg') || {}).hidden ? '' : (document.getElementById('loginMsg') || {}).textContent,
    sess: localStorage.getItem('va_sb_session'),
    view: (document.getElementById('view') || {}).textContent || '',
    hash: location.hash,
  }));
  const login = async () => {
    await page.evaluate(() => {
      document.getElementById('email').value = 'ops@vorlina.net';
      document.getElementById('pw').value = 'whatever';
      document.getElementById('loginForm').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    });
    await new Promise(r => setTimeout(r, 400));
  };

  /* ── T1 未登录：门禁必须关着，hash 也进不去 ── */
  await page.goto(URL_PAGE + '#/products', { waitUntil: 'networkidle0' });
  let s = await state();
  check('T1 未登录时停在登录页', s.loginHidden === false && s.appHidden === true, JSON.stringify({ loginHidden: s.loginHidden, appHidden: s.appHidden }));
  check('T1 未登录时 #view 不渲染任何视图', s.view.trim() === '', s.view.slice(0, 60));
  check('T1 未登录时无会话残留', !s.sess);

  /* ── T2 密码错：必须拒绝，且不留半截会话 ── */
  S.signin = 'badcreds';
  await login();
  s = await state();
  check('T2 密码错 → 仍在登录页', s.appHidden === true);
  check('T2 密码错 → 提示中文错误文案', /邮箱或密码不正确/.test(s.msg), s.msg);
  check('T2 密码错 → 不留会话', !s.sess, String(s.sess));
  S.signin = 'ok';

  /* ── T3 非成员：登录成功但不在 members 里 → 拒绝 ── */
  S.member = 'none';
  await login();
  s = await state();
  check('T3 非成员 → 仍在登录页', s.appHidden === true);
  check('T3 非成员 → 提示不是团队成员', /不是团队成员/.test(s.msg), s.msg);
  check('T3 非成员 → 不留会话', !s.sess, String(s.sess));
  S.member = 'staff';

  /* ── T4 有效成员：进入主框架，顶栏显示真实身份 ── */
  await login();
  s = await state();
  check('T4 有效成员 → 进入主框架', s.appHidden === false && s.loginHidden === true);
  check('T4 顶栏显示真实姓名', s.who === '林晓', s.who);
  check('T4 顶栏显示真实角色', s.role === 'role: 业务员', s.role);
  check('T4 落库会话键 va_sb_session', !!s.sess && /AT-1/.test(s.sess), String(s.sess).slice(0, 40));
  check('T4 顶栏不再出现硬编码的「小林」', !/小林/.test(s.who + s.role));

  /* ── T5 刷新保持登录 ── */
  await page.reload({ waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 300));
  s = await state();
  check('T5 刷新后保持登录（不回到登录页）', s.appHidden === false && s.who === '林晓');

  /* ── T6 令牌过期 + refresh 可用 → 自动续期 ── */
  S.token = 'old'; S.refreshed = false;
  await page.reload({ waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 400));
  s = await state();
  check('T6 令牌过期 → 自动用 refresh_token 续期并进入', s.appHidden === false && s.who === '林晓');
  check('T6 续期后会话换成新令牌', !!s.sess && /AT-2/.test(s.sess), String(s.sess).slice(0, 40));

  /* ── T7 refresh 也失败 → 回登录页并清会话 ── */
  S.token = 'old'; S.refresh = 'fail'; S.refreshed = false;
  await page.reload({ waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 400));
  s = await state();
  check('T7 续期失败 → 回到登录页', s.appHidden === true && s.loginHidden === false);
  check('T7 续期失败 → 清空会话', !s.sess, String(s.sess));
  S.token = 'ok'; S.refresh = 'ok'; S.refreshed = false;

  /* ── T8 退出：清会话 + 回登录页 ── */
  await login();
  await page.reload({ waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 300));
  await page.click('#logout');
  await new Promise(r => setTimeout(r, 200));
  s = await state();
  check('T8 退出 → 回到登录页', s.appHidden === true && s.loginHidden === false);
  check('T8 退出 → localStorage 会话被清掉', !s.sess, String(s.sess));

  /* ── T9 角色说明随真实角色变化（页面不许说谎）── */
  S.member = 'staff';
  await login();
  await page.evaluate(() => { location.hash = '#/releases'; });
  /* 等「回滚可用/不可用」真的渲染出来再断言 —— 固定 sleep 会读到「正在从仓库读取内容…」
     （2026-09-23 全量回归实测翻车；等不到就超时判红，不掩盖真失败） */
  await page.waitForFunction(
    () => /回滚(可用|不可用)/.test(document.getElementById('view').textContent),
    { timeout: 15000 }).catch(() => {});
  s = await state();
  check('T9 业务员看到「回滚不可用」', /回滚不可用/.test(s.view), s.view.slice(0, 120));
  await page.click('#logout'); await new Promise(r => setTimeout(r, 150));
  S.member = 'boss';
  await login();
  await page.evaluate(() => { location.hash = '#/releases'; });
  /* 等「回滚可用/不可用」真的渲染出来再断言 —— 固定 sleep 会读到「正在从仓库读取内容…」
     （2026-09-23 全量回归实测翻车；等不到就超时判红，不掩盖真失败） */
  await page.waitForFunction(
    () => /回滚(可用|不可用)/.test(document.getElementById('view').textContent),
    { timeout: 15000 }).catch(() => {});
  s = await state();
  check('T9 boss 看到「回滚可用」', /回滚可用/.test(s.view), s.view.slice(0, 120));
  check('T9 boss 顶栏角色正确', s.role === 'role: boss', s.role);

  /* ── T10 页面里不留「已接真实登录」的反面陈述 ── */
  const html = await page.content();
  check('T10 不再出现「骨架演示 / 点登录直接进」旧文案', !/骨架演示|还没有接 Supabase/.test(html));

  /* ── T13 登录后 11 个路由全部渲染（补丁不该弄坏任何视图）── */
  S.member = 'staff';
  await page.click('#logout').catch(() => {}); await new Promise(r => setTimeout(r, 150));
  await login();
  const ids = await page.evaluate(() => NAV.filter(n => n.id).map(n => n.id));
  const bad = [];
  for (const id of ids) {
    await page.evaluate(i => { go(i); }, id);
    await new Promise(r => setTimeout(r, 60));
    const t = await page.evaluate(() => ({
      n: document.getElementById('view').textContent.trim().length,
      h1: (document.querySelector('#view h1') || {}).textContent || '',
    }));
    if (!t.n || !t.h1) bad.push(id + '→' + JSON.stringify(t));
  }
  check('T13 登录后全部路由渲染出标题', bad.length === 0 && ids.length === 11, 'ids=' + ids.length + ' 异常=' + bad.join(' | '));

  /* ── T12 go() 门禁本身（直接调用全局 go()，否则这道兜底闸门没有任何断言覆盖）──
     变异测试发现的缺口：把 `if (!SESSION) return` 摘掉后，T1 依然全绿 ——
     因为未登录时 boot() 根本不会调用 go()。要证明这道闸门有效，只能直接打它。 */
  await page.click('#logout'); await new Promise(r => setTimeout(r, 150));
  const beforeGo = await page.evaluate(() => document.getElementById('view').textContent);
  await page.evaluate(() => { go('products'); });
  await new Promise(r => setTimeout(r, 150));
  const afterGo = await page.evaluate(() => document.getElementById('view').textContent);
  check('T12 未登录时直接调用 go() 不渲染视图',
        afterGo === beforeGo && !/产品与分类/.test(afterGo),
        'before=' + JSON.stringify(beforeGo.slice(0, 24)) + ' after=' + JSON.stringify(afterGo.slice(0, 24)));

  /* ── T11 零 JS 报错 ── */
  check('T11 全程零 JS 未捕获异常', jsErrors.length === 0, jsErrors.slice(0, 3).join(' | '));
  check('T11 4xx 噪声确实来自夹具（证明排除的不是真空）', netNoise.length >= 2, 'netNoise=' + netNoise.length);

  await browser.close();

  console.log('\n════════ vorlina-admin 登录门禁验证 ════════');
  console.log(results.join('\n'));
  console.log('──────────────────────────────────────────');
  console.log('RESULT: ' + (fail === 0 ? 'ALL PASS' : 'FAIL (' + fail + ')') + '  通过 ' + pass + ' / 失败 ' + fail);
  process.exit(fail === 0 ? 0 : 1);
}

main().catch(e => { console.error('测试脚本异常：', e); process.exit(2); });
