# MedicalChannelAI 天津 Pilot 单机运行边界 v0.1

状态：`FROZEN_FOR_SINGLE_HOST_PILOT`  
生产就绪：`false`

## 目标

首批天津 Pilot 优先验证“公开采购事实 → 客户画像匹配 → Today Actions → 销售动作”的工作流，不为少量客户提前引入复杂账号平台、分布式数据库或多服务器编排。

## 首版拓扑

```text
浏览器 H5
  │  同域 HTTPS
  ├─ /              -> 静态 web/
  └─ /api/*         -> 反向代理
                         │
                         v
                  pilot_server.py
                  127.0.0.1:8787
                         │
                         v
                  persistent pilot.sqlite
                    ├─ customer profiles (tenant-private)
                    ├─ public opportunities (shared public facts)
                    ├─ public evidence (shared public facts)
                    ├─ one-time invites
                    ├─ opaque sessions
                    ├─ Agnes dispatch queue
                    └─ Agnes terminal results
```

H5 构建时使用：

```text
VITE_API_BASE_URL=/api
```

后端默认只监听 `127.0.0.1`。公网 HTTPS/TLS、限流、域名和静态文件由前置反向代理处理。

## 身份与登录

Pilot 不存客户密码，也不接受浏览器传入 tenant/profile 作为身份。

流程：

```text
管理员确认 tenant/profile 已存在
  -> 生成一次性高熵 invite
  -> 客户打开 /login#code=<invite>
  -> fragment 不随 HTTP/Referer 发出，H5 读取后立即从地址栏移除
  -> POST /api/auth/redeem {code}
  -> invite 原子标记已使用
  -> 服务端生成随机 opaque session
  -> 浏览器只收到 __Host-mcai_session
  -> Secure + HttpOnly + SameSite=Strict
```

数据库只保存 invite/session token 的 SHA-256，不保存原始 token。Session 默认 7 天，invite 默认 30 分钟；均可按受控参数缩短。Logout 会撤销当前 session 并清 Cookie。

## Tenant / Public Fact 数据边界

### Tenant-private

- customer profile
- hospital relationships
- product capabilities
- partnering policy
- 后续 follow-up / reminders / user state

### Shared public facts

- public procurement opportunities
- official evidence
- public lifecycle facts
- public institution evidence

相同政府采购项目不得为每个客户复制一份。匹配阶段读取同一份公开事实，再结合当前 tenant/profile 的私有画像计算。

`today_repo.py` 会拒绝把 `tenant_id/profile_id/customer_context/followup/...` 等客户私有字段写入 public opportunity/evidence 表。

## HTTP 边界

公开浏览器入口只允许：

```text
POST /api/auth/redeem
POST /api/auth/logout
GET  /api/today
GET  /api/opportunity/:id
```

`/api/today` 与 `/api/opportunity/:id` 的 tenant/profile 只能来自已验证 session。Query/header 中伪造的 tenant/profile 不参与身份解析。

默认：

- same-origin；不打开 permissive CORS；
- `Cache-Control: no-store, private`；
- 内部异常正文不返回浏览器；
- Public View 不允许 model input / task / lease / Provider / API Key 等内部字段；
- H5 再做一次递归 fail-closed 检查。

反向代理必须对 `/api/auth/redeem` 增加速率限制。

## 管理员 Bootstrap

参考入口：

```text
python -m tools.medical_pilot.pilot_admin --db /srv/medical/pilot.sqlite profile-put --file profile.json
python -m tools.medical_pilot.pilot_admin --db /srv/medical/pilot.sqlite opportunity-put --file opportunity.json
python -m tools.medical_pilot.pilot_admin --db /srv/medical/pilot.sqlite evidence-put --file evidence.json
python -m tools.medical_pilot.pilot_admin --db /srv/medical/pilot.sqlite invite --tenant <tenant> --profile <profile> --login-url https://example.com
```

邀请码只显示一次，不得提交到 GitHub、Issue、日志或客服工单。

参考 API 服务：

```text
python -m tools.medical_pilot.pilot_server --db /srv/medical/pilot.sqlite --host 127.0.0.1 --port 8787
```

## 明确不是当前生产能力

以下仍未完成，因此 `production_ready=false`：

- 真实 Source collector 自动持续写入 `today_repo`；当前 repository/bootstrap 已实现，但采集持久化 wiring 仍待接；
- tenant-safe 服务端 follow-up/reminder；当前 H5 跟进仍 local-only；
- grounded on-demand outreach 正式 API；
- 真实附件 bytes 捕获；
- CI runner 的真实 Python/TypeScript/build PASS；
- 正式多用户成员/角色/审计体系；
- 横向多服务器共享 queue/lease/result/session/repository Store。

## 禁止的部署方式

**禁止**把当前 SQLite runtime 直接复制到多个 VPS、多个容器或多个无共享磁盘的 Serverless 实例。

**禁止**把 Vercel Function 的本地文件系统当作当前 Pilot SQLite 的持久化数据库。

需要横向扩展时，必须先把以下接口换为共享原子持久化实现：

- TodayActionsRepository
- SessionStore / InviteStore
- AgnesDispatchQueue
- AgnesTaskResultStore
- AgnesLeaseStore

首版天津 Pilot 单机运行不受此项阻塞。
