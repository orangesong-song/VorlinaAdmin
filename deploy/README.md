# VORLINA 后台 · 第 3 步发布链路（部署草稿 · 待钥匙）

> 状态：**代码已写好，未部署。** 卡在两把钥匙 —— ① GitHub fine-grained token ② Cloudflare 部署通道。
> 钥匙到位后按本 runbook 操作，代码无需重写（前台 `CONTENT_BASE` 一个常量切换即可）。

## 一、你要准备的两样东西（详细点选路径）

### ① GitHub fine-grained PAT（用于 Worker 持 token 读写仓库 / 触发 Actions）

1. 登录 GitHub → 右上角头像 → **Settings** → 左下 **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**。
2. Token name：`vorlina-admin-publish`（能认出即可）。
3. Expiration：建议 **90 days**（别选 No expiration，不安全；到期前我提醒你轮换）。
4. **Resource owner**：选 **`orangesong-song`**（必须选对 owner，否则仓库列表里看不到 VorlinaSite）。
5. **Repository access**：选 **Only select repositories** → 搜并勾选 **`VorlinaSite`**（只这一个，**绝不选 All repositories**）。
6. **Repository permissions**（其余全部保持 No access）：
   - **Contents** → Read and write（Worker 要读 JSON + 提交 cms 分支）
   - **Actions** → Read and write（Worker 要 `workflow_dispatch` 触发发布）
   - ⚠️ 不要给 Administration / Pull requests / Workflows 等无关权限（最小权限）。
7. **Generate token** → **立刻复制**（只显示一次）→ 交给我把存进 Worker Secret `GITHUB_TOKEN`。

### ② Cloudflare 部署通道（把扩写后的 Worker 上线）

现有 Worker 在 `syannsong.workers.dev`（脚本名 `vorlina-inquiry-notify`，当初 Dashboard 建的，本机无 `wrangler.toml`）。两种选法：

**A. Dashboard 粘贴（推荐，最稳，不用装东西）**
1. 登录 dash.cloudflare.com → 左侧 **Workers & Pages** → 选 `vorlina-inquiry-notify`。
2. **Edit code** → 把本地扩写后的完整 `worker.js` 粘贴进去（替换旧版；路由在顶部）。
3. **Settings → Variables** → 加 Secret/Env（值见第二节）：
   `GITHUB_TOKEN`（①拿的 PAT）· `GH_OWNER`·`GH_REPO`·`GH_CMS_BRANCH`·`GH_MAIN_BRANCH`·`GH_PUBLISH_WORKFLOW`。
4. **Deploy / Save**。

**B. wrangler login（本机有 node 时）**
1. 终端：`npx wrangler login`（浏览器 OAuth 把本机绑到 CF 账号）。
2. 建 `wrangler.toml`：`name = "vorlina-inquiry-notify"` + `account_id` + `compatibility_date`。
3. `npx wrangler deploy` → ⚠️ **整体替换脚本**，必须基于本地真源副本（`vorlina-new/data/inquiry-worker/worker.js` + 扩写路由），部署后验旧路由 `/enquiry`、`/notify` 仍工作。

⚠️ **不冲突 Supabase**：`GITHUB_TOKEN` 是 GitHub 的、Supabase 的 key 是另一套，Worker 里各走各的请求，互不影响。

### ③ 后台站点本身也要建一个 CF Pages 项目（容易漏）

Worker 只是"内容读写 + 发布"那一层的钥匙；**后台界面 `vorlina-admin/` 自己也要部署**到一个独立的 CF Pages 项目 `vorlina-admin.pages.dev`（不能放进 VorlinaSite 的 `preview/`）：
1. CF → **Workers & Pages** → **Create** → **Pages** → 连 GitHub 仓库 `vorlina-admin`（这是另一个仓库，不是 VorlinaSite）。
2. Build command：**留空**；Output directory：**`/`（根目录）**（后台是静态单页，无构建）。
3. 部署后 `vorlina-admin.pages.dev` 即后台地址。

## 二、Worker 扩写（worker-content-publish.js）

现有 Worker 在 `syannsong.workers.dev`（脚本名 `vorlina-inquiry-notify`）。扩写 = 在同账号同脚本上**加路由**，不新建第二个。

1. 打开 `vorlina-new/data/inquiry-worker/worker.js`（本地真源副本，583 行）。
2. 把第 74–104 行的 `export default { async fetch ... }` 整段替换为 `worker-content-publish.js` 顶部【ROUTER 替换块】。
3. 把 `worker-content-publish.js` 其余内容追加到文件末尾。
4. 在 CF Dashboard（或 wrangler.toml）补 env：
   - `GITHUB_TOKEN`（上面拿的 PAT）
   - `GH_OWNER=orangesong-song` · `GH_REPO=VorlinaSite` · `GH_CMS_BRANCH=cms` · `GH_MAIN_BRANCH=main` · `GH_PUBLISH_WORKFLOW=publish.yml`
5. 部署。
6. **必验（回归！）**：`/enquiry` 探针仍 200 · `/notify` 收信仍正常 · 新增 `/content` GET 返回仓库 JSON · `/publish` 触发后 Actions 跑通。
   - ⚠️ `wrangler deploy` 会整体替换脚本 ⇒ 必须基于本地副本加路由，部署后验旧路由。

## 三、GitHub Actions（publish.yml）

1. 把 `publish.yml` 放进 VorlinaSite 仓库 `.github/workflows/publish.yml`（cms 或 main 分支都行，dispatch 用 `ref: main`）。
2. **分支保护**（方案硬约束）：`main` 只接受 Actions 提交。
   - Settings → Branches → 保护 `main` → 勾 "Require a pull request" 不适用（我们是 merge）；
   - 改用：Actions 提交用 `GITHUB_TOKEN` 带 `permissions: contents:write`，人工直接 push 会因 RLS/保护被拒。
   - 或加一条校验 step：提交者非 `github-actions[bot]` 时 `exit 1`。
3. **cms 分支预览**：CF Pages 对 cms 分支自动出 `cms.vorlinasite.pages.dev`（后台内嵌 iframe 预览），无需额外 workflow。

## 四、闸门映射（已坐实，不是占位）

⚠️ **关键事实**：`build.py` 只暴露 4 个子命令（`build` / `check` / `sync` / `version`），
**没有** `linkcheck` / `cjk` / `slugcheck` / `leak`。所以闸门 2–5 由独立脚本
`VorlinaSite 仓库的 build/guards.py` 提供（单参数子命令，非零退出即阻断 Actions 提交）。

| 闸门 | 判据 | Actions 里跑的命令 | 现状 |
|---|---|---|---|
| 1 漂移 | 全站 39 页 × 4 公共段字节级 + 标签配平 | `python build/build.py check` | ✅ 已验证 |
| 2 断链 | 站内链接 0 死链（外链/mailto/tel/#锚点/`/cdn-cgi/` 跳过） | `python build/guards.py linkcheck` | ✅ 现预览 40 HTML 全过 |
| 3 CJK | 渲染可见 CJK = 0（注释/script/style/`pvbar` 除外） | `python build/guards.py cjk` | ✅ 现预览可见 CJK = 0 |
| 4 slug | `catalog-data.js` 的 slug 与 `slugify(nameEn)` 16/16 + 落地页存在 | `python build/guards.py slug` | ✅ 16/16 |
| 5 泄漏 | `{{V}}` / `{{P}}` 0 处 | `python build/guards.py leak` | ✅ 0 |

⚠️ **部署前必须确认 `build/guards.py` 已随本次发布提交进 VorlinaSite 仓库** ——
publish.yml 在 Actions 里 `checkout` 的是 VorlinaSite，`guards.py` 不在仓库里 Actions 会直接报「找不到文件」而失败。
（它在 `vorlina-new/build/guards.py`，与 `build.py` 同目录。）

ℹ **非阻塞发现**：现预览的 HTML 注释里含 8852 个中文字（不渲染，但会随站发到客户端、
暴露内部笔记如"首页 head 是本文件手写的"）。闸门 3 已正确把它排除在判据外，不影响上线；
但建议后续清理注释（可加一个 `gate6 · 注释无 CJK` 当卫生项，目前未做）。

## 五、前台切换（代码一行不用改）

后台 `index.html` 里 `CONTENT_BASE`：
- 本地桩：`http://127.0.0.1:8778/content`（现在）
- 生产：`https://<worker>.workers.dev/content`（钥匙到位后，URL 带 `?cb=` 或 localStorage `va_content_base` 切）
- 发布按钮的 `disabled` 逻辑：检测到 `CONTENT_BASE` 是 Worker 地址且 Worker 探活 `/` 返回 `content:true` 才解禁。

## 六、验证清单（上线前）

- [ ] Worker `/` 探针 `ready.content = true`
- [ ] 后台总览 `srcTag()` 显示「真源 15/15 · v<新版本>」
- [ ] 保存一次 → cms 分支多一个 commit → cms 预览 URL 更新
- [ ] 点发布 → Actions 跑通 5 闸门 → main 更新 → vorlina.net 出新版本（带 `?v=`）
- [ ] 回滚按钮非 boss 角色点被拒（403 role_denied）
- [ ] `/enquiry`、`/notify` 旧链路未被破坏
