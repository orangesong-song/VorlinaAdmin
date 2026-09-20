# VORLINA 后台 · 第 3 步发布链路（部署草稿 · 待钥匙）

> 状态：**代码已写好，未部署。** 卡在两把钥匙 —— ① GitHub fine-grained token ② Cloudflare 部署通道。
> 钥匙到位后按本 runbook 操作，代码无需重写（前台 `CONTENT_BASE` 一个常量切换即可）。

## 一、你要准备的两样东西

| 钥匙 | 怎么拿 | 用途 |
|---|---|---|
| GitHub fine-grained PAT | GitHub → Settings → Developer settings → PAT → Fine-grained，只选仓库 `orangesong-song/VorlinaSite`，权限 `Contents:write` + `Actions:write` | 存进 Worker Secret `GITHUB_TOKEN` |
| Cloudflare 部署通道 | 现有 Worker 在 `syannsong.workers.dev`（Dashboard 建的，本机无 wrangler.toml）。继续走 **Dashboard 粘贴**最稳；或 `wrangler login` 后 `wrangler deploy` | 把扩写后的 Worker 上线 |

⚠️ **新增 Secret 不冲突 Supabase**：`GITHUB_TOKEN` 是 GitHub 的，Supabase 的 key 是另一套。两个互不影响。

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
