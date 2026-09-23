#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vorlina-admin · vadmin-019b「失败信息别再说得含糊 + 文档去重」
2026-09-23

① 上传失败的「网络错误」太含糊 —— CORS 预检被拦时浏览器只给 TypeError
   "Failed to fetch"，运营和我们都看不出是后端没放行方法。补一句可操作提示。
② deploy/README.md 第「八」节整段重复了两遍（141-154 与 156-169 完全相同），
   删重复并补第「九」节：CORS 方法白名单事故 + 一条免鉴权探针命令 + 重贴流程。
"""
import io

def rep(s, old, new, n=1, tag=''):
    c = s.count(old)
    assert c == n, '断言失败[%s]：期望 %d、实际 %d ->\n%r' % (tag, n, c, old[:120])
    return s.replace(old, new)

# ── ① 上传失败提示可操作化 ──────────────────────────────────
F = 'index.html'
s = io.open(F, encoding='utf-8').read()
s = rep(s, """    } catch(e){ failed.push((f.name || '(未命名)') + '（网络错误）') }""",
"""    } catch(e){
      /* vadmin-019b：预检被拦时浏览器只说 Failed to fetch，运营看不出是后端没放行方法 */
      const net = /Failed to fetch|NetworkError|Load failed/i.test(String(e && e.message || e));
      failed.push((f.name || '(未命名)') + '（网络错误' + (net ? '：请求根本没发出去 —— 多为 Worker 未放行该请求方法（重贴后端代码）或网络不通' : '') + '）');
    }""", tag='fe.uploadErrHint')
io.open(F, 'w', encoding='utf-8').write(s)
print('OK · index.html 上传失败提示已可操作化')

# ── ② README 去重 + 补第九节 ────────────────────────────────
F = 'deploy/README.md'
s = io.open(F, encoding='utf-8').read()
H = '## 八、后台自身的 git 通道（2026-09-23 打通）'
assert s.count(H) == 2, '期望重复两次、实际 %d 次' % s.count(H)
s = s[:s.rindex(H)].rstrip() + '\n'          # 砍掉重复的那一份（保留第一份）
assert s.count(H) == 1

s += """
## 九、CORS 方法白名单（vadmin-019 · 2026-09-23 事故）

**事故**：后台在线上传永远失败、媒体库「移除」与「变更对比」也失败，页面只报「网络错误」。
**真因**：Worker 的 `corsFor()` 按 `kind` 给 `Access-Control-Allow-Methods`，而 `/media/*`、`/changes`
都落进默认分支 `'GET,OPTIONS'` —— 浏览器 **预检阶段**就把 POST / DELETE / PUT 拦死，
真正的请求根本没发出去。**跨域场景下，「路由存在且逻辑正确」≠「浏览器会发这个请求」。**
**修法**：`corsFor` 方法白名单统一 `GET,POST,PUT,DELETE,OPTIONS`（所有写路由都要求 Supabase JWT，
放宽方法不弱化鉴权）。

**免鉴权探针（发版前后各跑一次，10 秒判定）**：

```
# 预检必须回 POST —— 回 'GET,OPTIONS' 就是没生效
curl -s -X OPTIONS https://notify.vorlina.net/media/upload \\
  -H 'Origin: https://admin.vorlina.net' \\
  -H 'Access-Control-Request-Method: POST' \\
  -H 'Access-Control-Request-Headers: authorization' -D - -o /dev/null | grep -i 'allow-methods'

# 健康位（R2 绑定与否）
curl -s https://notify.vorlina.net/ | python3 -m json.tool
```

**为什么本地 E2E 测不出来**：`serve-local.py` 与页面同源，同源请求**不触发预检** ——
97 条断言全绿也照样漏。**跨域行为只能探线上，或让桩站换端口制造跨域。**

**重贴流程**：`deploy/worker.merged.js` 整文件全选复制 → CF Dashboard → Workers → vorlina-inquiry-notify
→ 编辑代码 → 全选覆盖 → Deploy（改后端必须重贴，git push 不会带上 Worker）。
"""
io.open(F, 'w', encoding='utf-8').write(s)
print('OK · README 去重完成并补第九节')
