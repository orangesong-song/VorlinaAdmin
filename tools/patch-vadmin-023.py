# -*- coding: utf-8 -*-
"""vadmin-023：① 后台版本戳可见（单一真源）② 文章正文块改为平铺渲染（去掉套娃）。

两件事都来自用户实拍：
- 截图 1：右下角没有版本戳，只看到站点版本串 20261103b —— 两个版本号混淆。
  版本戳原只在编辑弹窗标题里一行小灰字，且侧栏/总览都没有，运营根本不知道"当前跑的是哪版后台"。
- 截图 2：文章编辑页 块→对象→v→rows→行→第N格 五层框叠在一起，无法阅读。

规则：每一处锚点必须命中恰好 1 次，任一失败立即停（不半改）。
"""
import io

F = 'index.html'
s = io.open(F, encoding='utf-8').read()
ORIG_LEN = len(s)


def rep(old, new, why=''):
    global s
    c = s.count(old)
    assert c == 1, '锚点命中 %d 次（期望 1）%s: %r' % (c, why, old[:80])
    s = s.replace(old, new, 1)


# ── ① 版本号：单一真源 ADMIN_VER ──────────────────────────────
rep("""<script>
/* ══════════════════════════════════════════════════════════════
   阶段状态（2026-09-20）：""",
    """<script>
/* 后台界面版本 —— **唯一真源**：弹窗头 / 侧栏底部 / 总览都读它。
   每次改前端必须只改这一行（以前散落硬编码，改一处忘一处）。 */
const ADMIN_VER = 'vadmin-023';
/* ══════════════════════════════════════════════════════════════
   阶段状态（2026-09-20）：""",
    'ADMIN_VER 常量')

rep("""      <span class="mono" style="font-size:10px;color:var(--muted)">vadmin-022</span>""",
    """      <span class="mono" id="edVer" style="font-size:10px;color:var(--muted)"></span>""",
    '弹窗版本戳改为由 ADMIN_VER 填充')

# 侧栏底部：常驻版本号（这是用户"找不到版本戳"的直接解决）
rep("""    `<button class="rail-item" data-go="settings"${active === 'settings' ? ' aria-current="page"' : ''}>设置与成员</button>` +
    `<button class="rail-item dim" id="logout2">退出登录</button>`;""",
    """    `<button class="rail-item" data-go="settings"${active === 'settings' ? ' aria-current="page"' : ''}>设置与成员</button>` +
    `<button class="rail-item dim" id="logout2">退出登录</button>` +
    `<div class="rail-ver" title="后台界面版本 —— 与站点内容版本串（如 20261103b）是两件事">后台界面 <span class="mono">${ADMIN_VER}</span></div>`;""",
    '侧栏底部版本号')

# 总览「当前版本」卡：把两个版本号并排放，并写明区别
rep("""            <div style="font-size:13px">仓库里的内容快照</div></div>""",
    """            <div style="font-size:13px">仓库里的内容快照</div>
            <div style="font-size:12px;color:var(--muted);margin-top:6px">后台界面版本
              <span class="mono" style="color:var(--ink)">${ADMIN_VER}</span> —— 与上面的站点版本串是两件事</div></div>""",
    '总览版本卡补后台版本')

# 弹窗头 / 侧栏的版本号在 boot 时统一写入（只写一处来源）
rep("""(async function boot(){
  const s = sbSession();""",
    """(async function boot(){
  const verEl = document.getElementById('edVer');
  if (verEl) verEl.textContent = ADMIN_VER;
  const s = sbSession();""",
    'boot 写入弹窗版本戳')


# ── ② 弹窗加宽：表格 4–5 列并排才不挤 ────────────────────────
rep("""width:min(880px,94vw);""", """width:min(1020px,96vw);""", '弹窗宽度')


# ── ③ CSS：正文块平铺样式 ────────────────────────────────────
css_add = io.open('/tmp/nb.css', encoding='utf-8').read()
rep("""  .ed-msg{padding:10px 20px;border-top:1px solid var(--line);min-height:40px;font-size:13px}""",
    """  .ed-msg{padding:10px 20px;border-top:1px solid var(--line);min-height:40px;font-size:13px}
""" + css_add,
    '正文块 CSS')


# ── ④ 正文块渲染器：插在 edNoteHTML 之前 ─────────────────────
nb_js = io.open('/tmp/nb_blocks.js', encoding='utf-8').read()
rep("""/* 文章分区表单：① 基本信息 ② 只读（slug / 编号 / 状态）③ 配图 ④ 正文块 */
function edNoteHTML(){""",
    nb_js + """/* 文章分区表单：① 基本信息 ② 只读（slug / 编号 / 状态）③ 配图 ④ 正文块 */
function edNoteHTML(){""",
    'edBlocksHTML 注入')


# ── ⑤ ④ 正文块改用新渲染器 ───────────────────────────────────
rep("""    + edSec('④ 正文块', ED_SEC_NOTE.blocks || '',
            edNodeHTML(base.concat('blocks'), n.blocks || [], '正文块', null, 'blocks'));""",
    """    + edSec('④ 正文块 · ' + (n.blocks || []).length + ' 块', ED_SEC_NOTE.blocks || '',
            edBlocksHTML(base.concat('blocks'), n.blocks || []));""",
    '④ 正文块调用')


# ── ⑥ 分区提示改写（说明新交互 + 为什么不能直接改类型）──────
rep("""  blocks:'正文按块排：h2 小标题 / p 段落 / ul 列表 / table 表格 / notice 提示。块可增删、可调序。',""",
    """  blocks:'一个块一个框，点标题行可收起。顶部按钮加新块，块内 ↑↓ 调序、复制、删。'
    + '「类型」是不能直接改的 —— 不同类型的数据结构不同（段落是一段文字、表格是行列），'
    + '要换类型就加一个新块把内容搬过去、再删掉旧的。',""",
    '④ 分区提示')


# ── ⑦ edRender：重绘后保持滚动位置（否则加块/调序会跳回顶部）──
rep("""function edRender(){
  if (!ED) return;
  document.getElementById('edTitle').textContent = ED.label + '　·　' + ED.path;
  const k = edKind();
  document.getElementById('edBody').innerHTML =""",
    """function edRender(){
  if (!ED) return;
  document.getElementById('edTitle').textContent = ED.label + '　·　' + ED.path;
  const k = edKind();
  const _body = document.getElementById('edBody');
  const _keep = _body ? _body.scrollTop : 0;   /* 加块/调序后重绘会把滚动拉回顶部，这里保住位置 */
  _body.innerHTML =""",
    'edRender 保滚动（1/2）')

rep("""    :                    edGenericHTML();
  document.getElementById('edWrap').hidden = false;
}""",
    """    :                    edGenericHTML();
  _body.scrollTop = _keep;
  document.getElementById('edWrap').hidden = false;
}""",
    'edRender 保滚动（2/2）')


# ── ⑧ 事件委托：加块 / 加行 / 加删列 / 折叠 ──────────────────
nb_ev = io.open('/tmp/nb_handlers.js', encoding='utf-8').read()
rep("""  if (heroBtn){ edSet(ED.doc, ED.sub.concat(['images','hero']), heroBtn.dataset.hero); edRender(); return }
  const opBtn = e.target.closest('[data-edop]');""",
    """  if (heroBtn){ edSet(ED.doc, ED.sub.concat(['images','hero']), heroBtn.dataset.hero); edRender(); return }
""" + nb_ev + """  const opBtn = e.target.closest('[data-edop]');""",
    '块操作事件')


io.open(F, 'w', encoding='utf-8').write(s)
print('✓ index.html 全部补丁命中（%d → %d 字节）' % (ORIG_LEN, len(s)))


# ── ⑨ admin.css：侧栏底部版本号样式 ─────────────────────────
CF = 'theme/css/admin.css'
c = io.open(CF, encoding='utf-8').read()
old = '.rail-foot{border-top:1px solid #2A2C33;padding:8px 0}'
assert c.count(old) == 1, 'rail-foot 锚点 %d 次' % c.count(old)
c = c.replace(old, old + """
.rail-ver{padding:8px 18px 4px;font-family:var(--mono);font-size:10px;letter-spacing:.06em;color:#5B6470}
.rail-ver .mono{color:#9C968E}""", 1)
io.open(CF, 'w', encoding='utf-8').write(c)
print('✓ admin.css 补 .rail-ver')
