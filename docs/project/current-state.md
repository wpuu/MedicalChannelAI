# MedicalChannelAI 当前状态

日期：2026-08-30  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION + TODAY_ACTIONS_TRUSTED_BACKEND + H5_AUTH_SINGLE_HOST_RUNTIME + PERSISTENT_DISCOVERY + SERVER_FOLLOWUP_INITIAL`  
生产就绪：**false**  
Draft PR：**#1（保持 Draft，不合并）**

## 当前真实规模

- 7 个运行时 P0 Source：4 `IMPLEMENTED`、3 `PARTIAL_IMPLEMENTATION`
- 50 条 VERIFIED 天津商机 regression fixture
- 15 条 Institution Evidence
- **37 份 Schema/合同**
- **71 组 deterministic unittest 模块已写入，尚未获得真实执行 PASS 证据**
- 真实官方附件 bytes=0；医疗附件 bytes=0
- 首条天津医疗附件精确官方 URL 已确认：`TGPC-2025-A-0164 / method=downEnId`，但 bytes/MIME/SHA 尚未取得
- Agnes benchmark 28 case，未执行
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`

## Today Actions 可信后端

当前链路：

`Public collector → event ledger → current opportunity projection → Match/Score → Today Actions internal → input SHA-256 → terminal result reuse → dispatch queue → global lease → Agnes Worker → grounded validation → terminal result → Public View`

已经具备：

- 最终 Today Action 最多5张；
- 只有最终卡片允许进入模型候选；
- 官方事实、Evidence、客户私有上下文、Priority、AI Decision 分离；
- 无 VERIFIED grounded fact 时阻止模型生成；
- 越权/无依据模型输出拒绝展示；
- immutable input task identity + terminal-result 幂等；
- SQLite dispatch queue / lease / result store 可用于单机 Pilot；
- 跨服务器共享原子 Store 仅在水平扩容前补，不阻塞天津 Pilot。

## Auth / API / H5

单机 Pilot 不依赖浏览器自报 tenant/profile：

- `session_auth.py`：随机 opaque session，数据库只存 SHA-256；
- `invite_auth.py`：一次性高熵 invite，默认30分钟，成功兑换后不可重放；
- Cookie：`__Host-mcai_session; Secure; HttpOnly; SameSite=Strict`；
- `auth_http.py`：invite redeem / logout；
- `today_actions_http.py`：GET `/today`、`/opportunity/:id`，身份必须来自 trusted principal；
- `today_repo.py`：客户画像 tenant-private；公开采购事实跨客户共享、不复制；
- `today_runtime.py`：同一单机 SQLite 绑定 repository/session/invite/follow-up/Agnes queue/result；
- `pilot_api.py` + `pilot_server.py`：same-origin `/api/*` 参考入口，默认只监听 `127.0.0.1:8787`；
- `web/`：`/login` + `/today` + `/opportunity/:id`；真实 API 401 自动回登录；Mock 模式仍可独立演示；
- API 模式顶部显示“天津 Pilot”，Mock 模式显示“演示数据”。

当前禁止把这套 SQLite runtime 直接复制到多 VPS、多容器或无共享磁盘 Serverless；Vercel Function 本地文件系统不能充当持久数据库。

## 服务端 Follow-up 已完成初版

新增：

- `followup_store.py`
- `followup_http.py`
- `medical-followup-state-public.schema.json`
- `GET /api/followup/:opportunity_id`
- `POST /api/followup/:opportunity_id`

边界：

- follow-up 是客户私有数据，**绝不写入 public opportunity/evidence**；
- tenant/profile 只能来自已认证 Session；浏览器 JSON 中出现 tenant/profile 会直接 400；
- 只有数据库中真实存在的 public opportunity 才允许建立 follow-up；
- 事件 append-only；当前状态从最新事件计算；
- 浏览器 mutation 使用 profile 级唯一 `mutation_id`；同 mutation+同 opportunity+同 payload 幂等重放不重复写；同 mutation 被换 opportunity 或换 payload 时返回409；
- 同一公开采购项目可以被不同 tenant/profile 分别跟进，状态完全隔离；
- NOT_FIT 原因使用冻结 code，并继续复用 `followup_feedback.py` 生成画像复核建议；`auto_apply_allowed=false`，绝不自动改客户画像；
- H5 API 模式已移除 follow-up localStorage，Top5 和详情会读取服务端状态，更新后可跨浏览器保存；
- Mock 模式仍保持本地 Demo 状态。

### Reminder 当前真实状态

`remind_at / next_followup_at` **已经服务端持久化**，但还没有 reminder delivery worker/消息推送，所以目前只能说“提醒时间已保存”，不能说“系统到点会通知”。

## Collector 自动持久化

已实现：

- `collector_ingest.py`
- `collector_store.py`
- `cli.py --db`

单个已登记官方详情 URL 可以直接：

`抓取 → 解析 → VERIFIED event/facts → public event ledger → lifecycle 重算 → 当前 factual projection → product taxonomy → institution enrichment → today_repo`

关键正确性边界：

- 先抓 AWARD、后补抓旧 TENDER，lifecycle 不会倒退；
- 同日低精度冲突保持 `CONFLICTED/UNKNOWN`；
- 产品 taxonomy、award items、租赁判断只取 current lifecycle event 的 VERIFIED facts，旧 scope 不污染新结果；
- “采购”本身不自动等于“非租赁”；没有明确证据保持 UNKNOWN；
- 天津财政三个已登记官方详情 host 与 registry/fetcher 已一致。

## Discovery：2/7 已可自动运行

### DISCOVERY_READY

1. `tjmugh_procurement` → 天津医科大学总医院专属采购 listing
2. `tj_first_central_hospital_procurement` → 天津市第一中心医院专属 listing

### DISCOVERY_NOT_READY

- `tj_government_procurement`：native list route 未解决；
- `tj_government_procurement_center`：采购公告 list classId/pagination 未解决；
- `ccgp_local_notices`：当前 canonical list 是全国地方公告，不能直接当天津列表；
- `ccgp_procurement_intent`：搜索 CAPTCHA / query contract 未固定；
- `tj_public_resource_exchange`：结果列表 discovery contract 未固定。

Detail parser 可用不代表 listing discovery 已安全可用。5 个 not-ready Source 不会因为 cadence 到点而被盲目调用。

## Persistent Discovery Runtime

`discovery_runtime.py`：

- listing 发现的 detail URL 持久化；
- 成功 detail 默认24h内不重复抓；
- detail 失败 15→30→60…分钟退避，最多240分钟；
- detail URL 自己失败不会错误增加整个 listing Source 的失败次数。

`discovery_scheduler.py`：

- 复用 `discovery_cadence.tianjin.v0.1.json`；
- Asia/Shanghai；
- 总医院稳定`:03`，一中心稳定`:11`；
- 工作日白天 EARLY_SIGNAL 基线15分钟，周末/夜间降频；
- listing/source 级失败扩大 regular cadence，成功清零；
- `07:31–07:43`、`12:46–12:58` 强刷窗口已接入；
- SQLite `(source_id, slot_id)` 原子 claim，重复 cron、进程重启、重叠 tick 不会重复同一 slot；
- 推荐每分钟调用一次幂等 tick：

```text
python -m tools.medical_pilot.discovery_scheduler --db /srv/medical/pilot.sqlite
```

当前 minute-granular；policy 中10% sub-minute jitter 尚未实际执行。

## CI / Build

最新代码验证触发点：HEAD `ba18867140991cdba541284a009f6e45d3789e7d`，Run `33294841225`：

- `web-build` Job `99212619274`：`runner_id=0 / steps=[] / failure`
- `python-pilot` Job `99212619366`：`runner_id=0 / steps=[] / failure`

因此仍然**没有执行 npm install、TypeScript、H5 build 或 Python tests**。71个 test modules 是“已写入”，不是 PASS。两个 failure 只能解释为 runner 未分配，不能解释为代码 assertion/build failure。

## Agnes

Pilot 固定：

- `agnes-2.5-flash`
- <=12 starts / 60s
- start spacing >=5s
- max in-flight=2
- 0–2s stable jitter
- provider start 前必须获得 global lease
- terminal READY/REJECTED 按 immutable input 幂等复用

API Key、模型路由、Provider 地址只属于服务端，不进入 H5/Public View。

## 通知

采购机会通知策略保持：08:10晨报；08:30–18:30高优先 VERIFIED 可即时；13:15增量；18:30后普通项目排次日晨报；紧急变化例外到21:30。

Discovery 与通知窗口彼此独立。Follow-up `remind_at` 目前只持久化，尚未接入通知派发。

## 天津政府采购 / Attachment

精确医疗附件入口：

`TGPC-2025-A-0164` → `https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=cehQ4qF6Unc%2A&method=downEnId`

必须保持：`URL confirmed != bytes confirmed`。当前医疗真实附件 bytes 仍为0。

TJGPC：

- `W008` 已确认是网上应答帮助，禁止用于 procurement discovery；
- 真正采购公告/结果 list classId 与 pagination 仍未可靠验证；
- 已停止盲猜 W00x。

## 下一步

1. Runner 或等价可信执行环境恢复后，真实执行71组 deterministic tests + H5 typecheck/build；
2. 把已持久化 `remind_at` 接入 tenant-safe reminder delivery planner，但没有真实通知执行证据前不标“提醒已完成”；
3. 冻结并实现 grounded on-demand outreach API；
4. 获得执行证据后，在单机服务器真实运行 discovery tick 并记录 listing/detail latency；
5. 逐个解决剩余5个 Source discovery contract，不猜 classId/pagination、不绕 CAPTCHA；
6. 捕获已知 `downEnId` 医疗附件真实 bytes；
7. 有 deterministic 执行证据后运行28个 Agnes benchmark；
8. H5 Pilot 验证后再决定微信原生小程序。
