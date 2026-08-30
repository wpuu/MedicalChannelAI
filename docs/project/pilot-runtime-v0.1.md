# MedicalChannelAI 天津 Pilot 单机运行边界 v0.1

状态：`FROZEN_FOR_SINGLE_HOST_PILOT`  
生产就绪：`false`

## 目标

首批天津 Pilot 优先验证“公开采购事实 → 客户画像匹配 → Today Actions → 销售动作”的工作流，不为少量客户提前引入复杂账号平台、分布式数据库或多服务器编排。

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
               │           ├─ one-time invites / opaque sessions
               v           ├─ Agnes dispatch queue
        pilot_server.py     └─ Agnes terminal results
        127.0.0.1:8787
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

- public procurement events / opportunities
- official evidence
- public lifecycle facts
- public institution evidence

相同政府采购项目不得为每个客户复制一份。匹配阶段读取同一份公开事实，再结合当前 tenant/profile 的私有画像计算。

`today_repo.py` 会拒绝把 `tenant_id/profile_id/customer_context/followup/...` 等客户私有字段写入 public opportunity/evidence 表；`collector_store.py` 的 public event ledger 同样拒绝客户私有字段。

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

## Collector → Repository

单 URL 入口已统一到：

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

`cli.py` 保留原 research-only JSON 用法，同时支持：

```text
python -m tools.medical_pilot.cli <official-detail-url> --db /srv/medical/pilot.sqlite
```

重要边界：

- lifecycle 由完整 event ledger 重算，旧公告晚到不能把 AWARD 回退成 TENDERING；
- 同日低精度冲突保持 `CONFLICTED/UNKNOWN`，不伪造先后顺序；
- 当前产品 taxonomy、award items、租赁判断只取当前 lifecycle event 的 VERIFIED facts；
- “采购”不等于“非租赁”：明确租赁词才 True，明确购置/购买/买断才 False，否则保持 UNKNOWN；
- 天津财政已登记的官方详情域名 `tjgp.cz.tj.gov.cn`、`ccgp-tianjin.gov.cn`、`www.ccgp-tianjin.gov.cn` 可作为受控入口/跳转目标，未登记 host 仍拒绝。

## Discovery readiness

当前只允许两个**专属、已验证 listing**自动 discovery：

```text
tjmugh_procurement
  https://www.tjmugh.com.cn/cgxxtzgg/index.shtml

tj_first_central_hospital_procurement
  https://www.tj-fch.com/ywgk/ynbx/index.shtml
```

以下 5 个 Source 仍明确 `DISCOVERY_NOT_READY`：

- `tj_government_procurement`：native list route 未解决；
- `tj_government_procurement_center`：采购公告 list classId/pagination 未解决；
- `ccgp_local_notices`：现有 canonical listing 为全国地方公告，不能直接投影为天津；
- `ccgp_procurement_intent`：搜索存在 CAPTCHA，自动 discovery/query contract 未固定；
- `tj_public_resource_exchange`：结果列表 discovery contract 未固定。

**Parser/detail URL 可用，不等于 discovery listing 已可安全自动化。** Scheduler 只遍历 `DISCOVERY_READY_LISTINGS`，不会因为 cadence policy 中存在某个 source_id 就绕过 readiness。

## 持久化 Discovery cadence

`discovery_runtime.py`：

- listing 发现的 detail URL 持久化进 SQLite；
- 成功 detail 默认 24 小时内不重复抓；
- detail 失败按 15→30→60…分钟退避，最大 240 分钟；
- detail 层失败不会错误地把整个 listing Source 判死。

`discovery_scheduler.py`：

- 复用 `discovery_cadence.tianjin.v0.1.json`；
- Asia/Shanghai 时区；
- 总医院稳定 `:03`、一中心稳定 `:11`；
- 工作日白天 EARLY_SIGNAL 基线 15 分钟；周末/夜间自动降频；
- listing/source 级连续失败扩大 regular cadence，成功后归零；
- `07:31–07:43`、`12:46–12:58` 强刷窗口使用 source offset 在窗口内稳定错峰，并可绕过普通 backoff；
- SQLite `PRIMARY KEY(source_id, slot_id)` 原子 claim，同一 host 上 cron 重叠、进程重启、重复 tick 不会重复执行同一个 slot；
- v0.1 为 minute-granular scheduler，策略中的 sub-minute jitter 尚未实际执行；当前依靠稳定 minute offset 避免同机 Source 同时起跑。

推荐由单机 cron/systemd timer **每分钟调用一次幂等 tick**：

```text
python -m tools.medical_pilot.discovery_scheduler --db /srv/medical/pilot.sqlite
```

不需要常驻 while-loop；调度状态和 slot claim 已持久化在数据库里。

## 管理员 Bootstrap

参考入口：

```text
python -m tools.medical_pilot.pilot_admin --db /srv/medical/pilot.sqlite profile-put --file profile.json
python -m tools.medical_pilot.pilot_admin --db /srv/medical/pilot.sqlite opportunity-put --file opportunity.json
python -m tools.medical_pilot.pilot_admin --db /srv/medical/pilot.sqlite evidence-put --file evidence.json
python -m tools.medical_pilot.pilot_admin --db /srv/medical/pilot.sqlite invite --tenant <tenant> --profile <profile> --login-url https://example.com
```

其中 `opportunity-put/evidence-put` 现在主要用于测试、bootstrap 与人工修复；已验证 collector 正常路径应优先走 `collector_ingest.py` 自动落库。

邀请码只显示一次，不得提交到 GitHub、Issue、日志或客服工单。

参考 API 服务：

```text
python -m tools.medical_pilot.pilot_server --db /srv/medical/pilot.sqlite --host 127.0.0.1 --port 8787
```

## 明确不是当前生产能力

以下仍未完成，因此 `production_ready=false`：

- 7 个 P0 Source 尚未全部拥有可验证的自动 discovery contract；目前只有 2/7 可自动 listing discovery；
- discovery scheduler 尚无真实服务器 cron/systemd 执行证据；
- tenant-safe 服务端 follow-up/reminder；当前 H5 跟进仍 local-only；
- grounded on-demand outreach 正式 API；
- 真实附件 bytes 捕获；
- CI runner 的真实 Python/TypeScript/build PASS；
- 正式多用户成员/角色/审计体系；
- 横向多服务器共享 queue/lease/result/session/repository/discovery Store。

## 禁止的部署方式

**禁止**把当前 SQLite runtime 直接复制到多个 VPS、多个容器或多个无共享磁盘的 Serverless 实例。

**禁止**把 Vercel Function 的本地文件系统当作当前 Pilot SQLite 的持久化数据库。

需要横向扩展时，必须先把以下接口换为共享原子持久化实现：

- TodayActionsRepository
- SessionStore / InviteStore
- public event/discovery ledgers
- AgnesDispatchQueue
- AgnesTaskResultStore
- AgnesLeaseStore

首版天津 Pilot 单机运行不受此项阻塞。
