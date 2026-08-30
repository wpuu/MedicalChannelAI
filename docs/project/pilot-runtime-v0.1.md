# MedicalChannelAI 天津 Pilot 单机运行边界 v0.1

状态：`FROZEN_FOR_SINGLE_HOST_PILOT`  
生产就绪：`false`

## 目标

首批天津 Pilot 优先验证“公开采购事实 → 客户画像匹配 → Today Actions → 销售动作 → 跟进历史 → 按需沟通话术”的工作流，不为少量客户提前引入复杂账号平台、分布式数据库或多服务器编排。

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
               v           ├─ private grounded outreach cache
        pilot_server.py     ├─ one-time invites / opaque sessions
        127.0.0.1:8787      ├─ Agnes dispatch queue / terminal results
               │            └─ shared Agnes global lease state
               │
               └─ server-only Agnes client
                  MCAI_AGNES_API_KEY
```

H5 构建时：

```text
VITE_API_BASE_URL=/api
```

后端默认只监听 `127.0.0.1`。公网 HTTPS/TLS、限流、域名和静态文件由前置反向代理处理。

## 身份与登录

Pilot 不存客户密码，也不接受浏览器传入 tenant/profile 作为身份。

```text
管理员确认 tenant/profile 已存在
  -> 一次性 invite
  -> /login#code=<invite>
  -> POST /api/auth/redeem {code}
  -> invite 原子标记已使用
  -> 随机 opaque session
  -> __Host-mcai_session
  -> Secure + HttpOnly + SameSite=Strict
```

数据库只保存 invite/session token 的 SHA-256，不保存原始 token。Session 默认7天，invite 默认30分钟。

## Tenant / Public Fact 数据边界

### Tenant/profile-private

- customer profile
- hospital relationships
- product capabilities
- partnering policy
- follow-up events / remind_at
- grounded outreach result cache

### Shared public facts

- public procurement events / opportunities
- official evidence
- public lifecycle facts
- public institution evidence

相同政府采购项目不得为每个客户复制一份。匹配、跟进和 outreach 都引用同一份公共事实，再结合当前 tenant/profile 私有信息。

## HTTP 边界

浏览器入口：

```text
POST /api/auth/redeem
POST /api/auth/logout
GET  /api/today
GET  /api/opportunity/:id
GET  /api/followup/:opportunity_id
POST /api/followup/:opportunity_id
POST /api/outreach/:opportunity_id
```

Today/follow-up/outreach 的 tenant/profile 都只能来自已验证 Session。

默认：

- same-origin；不打开 permissive CORS；
- `Cache-Control: no-store, private`；
- 内部异常正文不返回浏览器；
- Public View 不返回 model input / task / lease / Provider / API Key；
- H5 对真实 API 响应再做 fail-closed 字段检查。

反向代理必须对 `/api/auth/redeem` 和 `/api/outreach/*` 做合理速率限制；后者同时还受服务端 Agnes global lease 约束。

## Follow-up / Reminder

`followup_store.py` 使用 append-only tenant/profile-private 事件：

- `UNIQUE(tenant_id, profile_id, mutation_id)`；
- mutation hash 绑定 `opportunity_id + status + note + reason + remind_at`；
- 同 mutation / 同 payload 重放幂等；
- 同 mutation 换项目或 payload 返回409；
- public opportunity 必须真实存在；
- 同一公共项目的不同 tenant/profile 历史完全隔离；
- NOT_FIT 只能生成 profile review suggestion，`auto_apply_allowed=false`。

H5 API 模式已取消 follow-up localStorage；Mock 仍本地演示。

`remind_at` 已持久化，但**尚无 reminder delivery worker / 微信 / 邮件 / 浏览器推送**，所以只承诺“提醒时间已保存”。

## Grounded on-demand Outreach

### 浏览器请求边界

v0.1 只允许：

```text
POST /api/outreach/:opportunity_id
Body: {} 或空
```

禁止浏览器传：

- free-form prompt
- tone
- tenant/profile
- 自定义事实
- 模型名、Provider、API Key

### Grounding 链路

```text
trusted Session
  -> load tenant-private profile
  -> load shared public opportunity
  -> load VERIFIED evidence
  -> deterministic match/admission
  -> require VERIFIED buyer_name + project_name
  -> build locked outreach model input
  -> SHA-256 cache lookup
  -> acquire shared Agnes global lease
  -> Agnes selects allowlisted strategy/question/positioning codes
     + supporting fact_ids/profile paths only
  -> validate references
  -> server renders final Chinese draft
  -> cache immutable result
  -> H5 Public View
```

Agnes 不负责写最终销售文案，也不能创建、补全或猜测采购事实。最终中文话术由服务端模板渲染，并固定包含“不是医院官方表述、不代表中标概率或采购承诺”的边界；`requires_human_confirmation=true`。

相同 tenant/profile/opportunity 的 VERIFIED facts 与客户确认 context 不变时，locked input SHA-256 不变，重复点击直接复用私有缓存，不重复调用模型。

Outreach 与 Today Actions 共用同一个 `AgnesLeaseStore`，所以真实 Provider start 继续统一遵守：

- `agnes-2.5-flash`
- <=12 starts / 60s
- >=5s minimum spacing
- max in-flight=2
- on-demand outreach task priority=`INTERACTIVE_DEEP_DIVE`

### Provider 配置

服务端进程环境变量：

```text
MCAI_AGNES_API_KEY=<server-only key>
MCAI_AGNES_BASE_URL=<optional official /v1 endpoint>
```

`MCAI_AGNES_BASE_URL` 即使配置，也必须通过官方 Agnes host allowlist。Key 不得进入 GitHub、SQLite、H5、日志、Issue 或客服工单。

未配置 `MCAI_AGNES_API_KEY` 时，Pilot 其他功能仍启动；只有 outreach 返回503。这样不会因为可选模型动作阻断 Today/follow-up 基础工作流。

## Collector → Repository

```text
collector_ingest.py
  -> registered source + host allowlist
  -> source adapter parse
  -> VERIFIED event/facts
  -> collector_store.py public event ledger
  -> lifecycle resolver
  -> current-event factual projection
  -> deterministic product taxonomy
  -> VERIFIED institution enrichment
  -> SQLiteTodayActionsRepository
```

重要边界：旧公告晚到不回退 lifecycle；同日低精度冲突保持 `CONFLICTED/UNKNOWN`；taxonomy/award/rental 只取 current lifecycle event VERIFIED facts；普通“采购”不自动等于“非租赁”。

## Discovery readiness

自动 discovery 仍只有2/7：

```text
tjmugh_procurement
tj_first_central_hospital_procurement
```

其余5个保持 fail-closed：天津财政 native list、TJGPC classId/pagination、CCGP 天津范围、采购意向 CAPTCHA/query contract、天津公共资源结果列表 contract 都未解决。

`discovery_runtime.py` 已做 URL ledger、24h success recheck、15→30→60…最大240分钟 detail backoff；`discovery_scheduler.py` 已接 Asia/Shanghai cadence、强刷窗口及 `(source_id, slot_id)` 原子 claim。

推荐单机每分钟一次幂等 tick：

```text
python -m tools.medical_pilot.discovery_scheduler --db /srv/medical/pilot.sqlite
```

## Pilot API 启动

```text
MCAI_AGNES_API_KEY=<server-only-key> \
python -m tools.medical_pilot.pilot_server \
  --db /srv/medical/pilot.sqlite \
  --host 127.0.0.1 \
  --port 8787
```

如暂不测试真实 outreach，可不设置 `MCAI_AGNES_API_KEY`。

## CI 边界

为兼容现有测试的相对/绝对导入，`tools` 已显式成为 package，unittest discovery 使用仓库根目录作为 top-level：

```text
python -m unittest discover -s tools/medical_pilot -t . -p "test_*.py" -v
```

此修改仍未获得真实执行证据。最新 CI 继续在 runner 分配前失败，不能据此判断代码通过或失败。

## 明确不是当前生产能力

因此 `production_ready=false`：

- 7个 P0 Source 只有2/7自动 listing discovery；
- discovery scheduler 尚无真实服务器执行/latency 证据；
- reminder delivery 未实现；
- grounded outreach 代码链路已接通，但未获得 deterministic CI PASS，也未做真实 server-side Agnes smoke；
- 真实附件 bytes 捕获未完成；
- CI 尚无真实 Python/TypeScript/build PASS；
- 正式多用户成员/角色/审计体系未完成；
- 横向多服务器共享 Store 未完成。

## 禁止的部署方式

禁止把当前 SQLite runtime 复制到多个独立 VPS、容器或无共享磁盘 Serverless 实例。禁止用 Vercel Function 本地文件系统承载 Pilot 持久数据库。

水平扩展前必须将 Repository、Session/Invite、Followup、Outreach cache、Discovery ledger、Agnes queue/result/lease 等替换为共享原子持久化实现。首版天津 Pilot 单机运行不受此项阻塞。
