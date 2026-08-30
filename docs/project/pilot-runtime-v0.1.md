# MedicalChannelAI 天津 Pilot 单机运行边界 v0.1

状态：`FROZEN_FOR_SINGLE_HOST_PILOT`  
生产就绪：`false`

## 目标

首批天津 Pilot 优先验证“公开采购事实 → 客户画像匹配 → Today Actions → 销售动作 → 跟进历史”的工作流，不为少量客户提前引入复杂账号平台、分布式数据库或多服务器编排。

## 首版拓扑

```text
已验证公开 Source
  │
  ├─ collector_ingest.py
  ├─ collector_store.py / public event ledger
  └─ discovery_runtime.py + discovery_scheduler.py
                         │
                         v
浏览器 H5              persistent pilot.sqlite
  │  同域 HTTPS           ├─ public events / opportunities / evidence
  ├─ / -> 静态 web/       ├─ discovery URL / schedule ledgers
  └─ /api/* -> 反代       ├─ customer profiles (tenant-private)
               │           ├─ private follow-up events / remind_at
               v           ├─ one-time invites / opaque sessions
        pilot_server.py     ├─ Agnes dispatch queue
        127.0.0.1:8787      └─ Agnes terminal results
```

H5 构建时使用：

```text
VITE_API_BASE_URL=/api
```

后端默认只监听 `127.0.0.1`。公网 HTTPS/TLS、限流、域名和静态文件由前置反向代理处理。

## 身份与登录

Pilot 不存客户密码，也不接受浏览器传入 tenant/profile 作为身份。

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

数据库只保存 invite/session token 的 SHA-256，不保存原始 token。Session 默认7天，invite 默认30分钟；Logout 撤销当前 session 并清 Cookie。

## Tenant / Public Fact 数据边界

### Tenant/profile-private

- customer profile
- hospital relationships
- product capabilities
- partnering policy
- follow-up events
- remind_at / future reminder state

### Shared public facts

- public procurement events / opportunities
- official evidence
- public lifecycle facts
- public institution evidence

相同政府采购项目不得为每个客户复制一份。匹配阶段读取同一份公开事实，再结合当前 tenant/profile 私有画像计算。

`today_repo.py` 拒绝把 `tenant_id/profile_id/customer_context/followup/...` 等客户私有字段写入 public opportunity/evidence；`collector_store.py` 的 public event ledger 同样拒绝客户私有字段。Follow-up 独立存入 `medical_private_followup_events`。

## HTTP 边界

浏览器入口：

```text
POST /api/auth/redeem
POST /api/auth/logout
GET  /api/today
GET  /api/opportunity/:id
GET  /api/followup/:opportunity_id
POST /api/followup/:opportunity_id
```

所有 Today/follow-up tenant/profile 只能来自已验证 Session。Query/header/JSON 中伪造 tenant/profile 不参与身份解析；follow-up JSON 里出现这些额外字段会 fail-closed。

默认：

- same-origin；不打开 permissive CORS；
- `Cache-Control: no-store, private`；
- 内部异常正文不返回浏览器；
- Today Public View 不允许 model input / task / lease / Provider / API Key 等内部字段；
- follow-up public state 不返回 tenant/profile；
- H5 再做一次递归 fail-closed 检查。

反向代理必须对 `/api/auth/redeem` 增加速率限制。

## Follow-up / Reminder

`followup_store.py` 使用 append-only 私有事件：

- `medical_private_followup_events`
- 主身份：`tenant_id + profile_id + opportunity_id`
- 客户 mutation：`UNIQUE(tenant_id, profile_id, mutation_id)`
- mutation hash 同时绑定 `opportunity_id + status + note + reason + remind_at`
- 同 mutation / 同 payload 重放返回已有事件，不重复写；
- 同 mutation 换项目或换 payload 返回 `409 IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD`；
- 同一时间戳连续写入时按 SQLite `rowid DESC` 保证真正后写的事件是当前状态；
- public opportunity 必须真实存在才允许写 follow-up；
- tenant/profile 不同，即使面对同一 public opportunity，历史也完全隔离。

NOT_FIT 使用冻结 reason code。客户确认后的 NOT_FIT 可通过 `followup_feedback.py` 产生 profile review suggestion，但：

```text
auto_apply_allowed=false
```

任何反馈都不能自动篡改公开事实，也不能自动改客户画像。

H5 API 模式已取消 follow-up localStorage：Top5 与详情都读取服务端 follow-up state；Mock 模式仍保留本地演示。

`remind_at` 已持久化，但**尚无 reminder delivery worker / 微信 / 邮件 / 浏览器推送**，因此当前只承诺“提醒时间已保存”，不承诺“到点已通知”。

## Collector → Repository

```text
collector_ingest.py
  -> registered source + host allowlist
  -> source adapter parse
  -> VERIFIED event/facts
  -> collector_store.py public event ledger
  -> existing lifecycle resolver
  -> current-event factual projection
  -> deterministic product taxonomy
  -> VERIFIED institution enrichment
  -> SQLiteTodayActionsRepository
```

`cli.py` 支持：

```text
python -m tools.medical_pilot.cli <official-detail-url> --db /srv/medical/pilot.sqlite
```

重要边界：

- lifecycle 由完整 event ledger 重算，旧公告晚到不能把 AWARD 回退成 TENDERING；
- 同日低精度冲突保持 `CONFLICTED/UNKNOWN`；
- taxonomy、award items、租赁判断只取当前 lifecycle event 的 VERIFIED facts；
- “采购”不等于“非租赁”：明确租赁词才 True，明确购置/购买/买断才 False，否则 UNKNOWN；
- 天津财政已登记官方详情域名 `tjgp.cz.tj.gov.cn`、`ccgp-tianjin.gov.cn`、`www.ccgp-tianjin.gov.cn` 可作为受控入口/跳转目标，未登记 host 拒绝。

## Discovery readiness

仅两个专属、已验证 listing 自动 discovery：

```text
tjmugh_procurement
  https://www.tjmugh.com.cn/cgxxtzgg/index.shtml

tj_first_central_hospital_procurement
  https://www.tj-fch.com/ywgk/ynbx/index.shtml
```

以下5个 Source 仍 `DISCOVERY_NOT_READY`：

- `tj_government_procurement`：native list route 未解决；
- `tj_government_procurement_center`：采购公告 list classId/pagination 未解决；
- `ccgp_local_notices`：canonical listing 是全国地方公告，不能直接投影为天津；
- `ccgp_procurement_intent`：搜索 CAPTCHA，自动 discovery/query contract 未固定；
- `tj_public_resource_exchange`：结果列表 discovery contract 未固定。

Parser/detail URL 可用，不等于 listing discovery 已可安全自动化。Scheduler 只遍历 `DISCOVERY_READY_LISTINGS`。

## 持久化 Discovery cadence

`discovery_runtime.py`：

- detail URL 持久化；
- 成功 detail 默认24小时内不重复抓；
- detail 失败15→30→60…分钟退避，最大240分钟；
- detail 层失败不会错误地把整个 listing Source 判死。

`discovery_scheduler.py`：

- 复用 `discovery_cadence.tianjin.v0.1.json`；
- Asia/Shanghai；
- 总医院稳定`:03`、一中心稳定`:11`；
- 工作日白天 EARLY_SIGNAL 基线15分钟；周末/夜间降频；
- listing/source 连续失败扩大 regular cadence，成功归零；
- `07:31–07:43`、`12:46–12:58` 强刷窗口稳定错峰；
- SQLite `(source_id, slot_id)` 原子 claim，同一 host 重复 cron/进程重启不会重复执行同一 slot；
- v0.1 minute-granular，sub-minute jitter 尚未实际执行。

推荐单机 cron/systemd timer 每分钟调用一次：

```text
python -m tools.medical_pilot.discovery_scheduler --db /srv/medical/pilot.sqlite
```

## 管理员 Bootstrap

```text
python -m tools.medical_pilot.pilot_admin --db /srv/medical/pilot.sqlite profile-put --file profile.json
python -m tools.medical_pilot.pilot_admin --db /srv/medical/pilot.sqlite opportunity-put --file opportunity.json
python -m tools.medical_pilot.pilot_admin --db /srv/medical/pilot.sqlite evidence-put --file evidence.json
python -m tools.medical_pilot.pilot_admin --db /srv/medical/pilot.sqlite invite --tenant <tenant> --profile <profile> --login-url https://example.com
```

`opportunity-put/evidence-put` 主要用于测试、bootstrap 和人工修复；正常已验证 collector 优先走自动落库。

邀请码只显示一次，不得提交到 GitHub、Issue、日志或客服工单。

API 服务：

```text
python -m tools.medical_pilot.pilot_server --db /srv/medical/pilot.sqlite --host 127.0.0.1 --port 8787
```

## 明确不是当前生产能力

因此 `production_ready=false`：

- 7个 P0 Source 只有2/7拥有可验证自动 listing discovery；
- discovery scheduler 尚无真实服务器 cron/systemd 执行证据；
- follow-up 状态已服务端持久化，但 reminder delivery 尚未实现；
- grounded on-demand outreach 正式 API 未完成；
- 真实附件 bytes 捕获未完成；
- CI runner 尚无真实 Python/TypeScript/build PASS；
- 正式多用户成员/角色/审计体系未完成；
- 横向多服务器共享 queue/lease/result/session/repository/followup/discovery Store 未完成。

## 禁止的部署方式

禁止把当前 SQLite runtime 直接复制到多个 VPS、多个容器或多个无共享磁盘 Serverless 实例。

禁止把 Vercel Function 的本地文件系统当作当前 Pilot SQLite 持久数据库。

水平扩展前必须把以下接口换为共享原子持久化实现：

- TodayActionsRepository
- SessionStore / InviteStore
- FollowupStore
- public event/discovery ledgers
- AgnesDispatchQueue
- AgnesTaskResultStore
- AgnesLeaseStore

首版天津 Pilot 单机运行不受此项阻塞。
