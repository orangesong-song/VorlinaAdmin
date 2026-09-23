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
2. **Edit code** → 全选删掉旧代码 → **把 `deploy/worker.merged.js` 的全部内容原样粘贴进去** → Save。
   - ⚠️ 粘贴的是 **`worker.merged.js`**（已把扩写路由并入原 worker.js 的完整成品，754 行），
     **不是** `worker-content-publish.js`（那只是供审阅的扩写源码，直接贴会缺旧询盘逻辑的上下文且带注释块）。
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

**粘贴产物已合并好：`deploy/worker.merged.js`**（原 worker.js 583 行 + 扩写路由与 helper = 754 行）。
它由脚本从 `worker.js` + `worker-content-publish.js` 自动合并，已过三道断言（无函数重名 · `export default` 唯一 · `/content` `/publish` `/enquiry` 路由齐全）+ `node --check`。
**Dashboard 粘贴它、或 `wrangler deploy` 用它，二选一，不要再手工合并。**

在 CF Dashboard **Settings → Variables** 配 **6 个变量**（1 个 Secret + 5 个普通 Text；缺一个功能就降级，其中只有 `GITHUB_TOKEN` 是硬必需，其余 5 个代码里有同值默认，但**显式配上**避免隐式行为）：

| 变量名 | 类型 | Value（原样填） | 作用 |
|---|---|---|---|
| `GITHUB_TOKEN` | **Secret**（加密，选 Encrypt） | ①步骤拿的 fine-grained PAT（`github_pat_…` 开头） | 读/写仓库 JSON、触发 Actions |
| `GH_OWNER` | Text | `orangesong-song` | 仓库属主 |
| `GH_REPO` | Text | `VorlinaSite` | 仓库名 |
| `GH_CMS_BRANCH` | Text | `cms` | 后台保存落的分支 |
| `GH_MAIN_BRANCH` | Text | `main` | 发布目标分支 |
| `GH_PUBLISH_WORKFLOW` | Text | `publish.yml` | 要触发的 workflow 文件名 |

部署后 **必验（回归！）**：`GET /` 探针里 `content: true` · `/enquiry` 仍 200 · `/notify` 收信仍正常 · 带 `Authorization: Bearer <成员JWT>` 调 `/content?path=data/products.json` 返回 base64 · `/publish` 触发后 Actions 跑通。

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
| 6 注释卫生 | HTML 注释内 CJK = 0（条件注释除外） | `python build/guards.py comments` | ✅ 已清源（2026-09-20 全部译英，8852→0） |

⚠️ 闸门 6 的教训（2026-09-20 实测）：注释真源在 `build/partials` / `build/templates` / `build.py` 内联模板，
**且 `<!-- ============ Inquiry drawer ============ -->` 这条注释同时是 gate1 漂移守卫的 body-end 段锚点** ——
改它必须 `build.py` 的 `ANCHORS` 与 partial 两侧同步改，否则全站报漂移。**不要在 preview/ 上清注释**（= 制造漂移）。

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

## 七、媒体库直传（vadmin-013 · 2026-09-23）

后台「媒体库」页已支持运营上传图片 / 目录 PDF。**代码已就位，上线前需在 Cloudflare 补一步 R2 绑定**：

1. dash.cloudflare.com → **R2 Object Storage** → Create bucket → 名字建议 `vorlina-media`（免费额度 10GB 存储，够用很久）。
2. Workers & Pages → `vorlina-inquiry-notify` → **Settings → Bindings → Add** → 选 **R2 bucket**：
   - Variable name：**`MEDIA`**（必须一字不差，代码读的是 `env.MEDIA`）
   - Bucket：`vorlina-media`
3. 重新部署 Worker（粘贴新版 `deploy/worker.merged.js`，它已含 `/media/*` 四条路由）。
4. 验证：后台 → 媒体库 → 不再出现「Worker 还没绑定 R2 桶」提示，上传一张测试图 → 网格出现卡片。

**存储策略（双写，不换真源）**：
- 上传的图 ① 存 R2（后台预览 + 备份）② **同步写进 GitHub `cms` 分支的 `assets/img/<文件名>`**。
- 图进的是 cms 分支 = 和内容草稿同一条闸门，**上传不直接上线**，走「变更清单 → 发布」才进 main。
- 官网模板继续引用 `/assets/img/...`，**构建与模板零改动**。
- `GET /media/file/img/<名>` 免鉴权直读（`<img>` 请求带不了 Authorization）：R2 命中直出，miss 则回源 vorlina.net —— 所以后台所有缩略图都能立刻看到刚上传的图。
- 删除只删 R2（后台媒体库移除），**不同步删仓库** —— 删官网真源风险高，要走发布流程由人确认。

**限制**：单文件 ≤ 8MB；类型限 webp / jpg / png / avif / gif / svg / pdf；本地开发桩 `serve-local.py` 已实现同形 `/media/*`（落 `.local-drafts/media/`）。
