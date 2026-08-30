# MedicalChannelAI 当前状态

日期：2026-08-30  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION + TODAY_ACTIONS_TRUSTED_BACKEND + H5_AUTH_SINGLE_HOST_RUNTIME + PERSISTENT_DISCOVERY + SERVER_FOLLOWUP + GROUNDED_OUTREACH_INITIAL`  
生产就绪：**false**  
Draft PR：**#1（保持 Draft，不合并）**

## 当前真实规模

- 7 个运行时 P0 Source：4 `IMPLEMENTED`、3 `PARTIAL_IMPLEMENTATION`
- 50 条 VERIFIED 天津商机 regression fixture
- 15 条 Institution Evidence
- **38 份 Schema/合同**
- **75 组 deterministic unittest 模块已写入，尚未获得真实执行 PASS 证据**
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
- `today_runtime.py`：同一单机 SQLite 绑定 repository/session/invite/follow-up/outreach/Agnes queue/result/lease；
- `pilot_api.py` + `pilot_server.py`：same-origin `/api/*` 参考入口，默认只监听 `127.0.0.1:8787`；
- `web/`：`/login` + `/today` + `/opportunity/:id`；真实 API 401 自动回登录；Mock 模式仍可独立演示；
- API 模式顶部显示“天津 Pilot”，Mock 模式显示“演示数据”。

当前禁止把这套 SQLite runtime 直接复制到多 VPS、多容器或无共享磁盘 Serverless；Vercel Function 本地文件系统不能充当持久数据库。

## 服务端 Follow-up

已具备：

- `followup_store.py`
- `followup_http.py`
- `medical-followup-state-public.schema.json`
- `GET /api/followup/:opportunity_id`
- `POST /api/followup/:opportunity_id`

边界：

- follow-up 是客户私有数据，绝不写入 public opportunity/evidence；
- tenant/profile 只能来自已认证 Session；
- public opportunity 必须真实存在；
- 事件 append-only；当前状态从最新事件计算；
- `mutation_id` profile 级幂等，并绑定 opportunity + payload；
- 同一公开项目不同 tenant/profile 的跟进完全隔离；
- NOT_FIT 只产生画像复核建议，`auto_apply_allowed=false`；
- H5 API 模式已使用服务端状态，Mock 模式仍本地演示。

`remind_at / next_followup_at` 已持久化，但 reminder delivery worker/消息推送仍未实现，所以目前只能承诺“提醒时间已保存”。

## Grounded on-demand Outreach 已接通代码链路

真实 H5 的“生成沟通话术”不再停留在 `OUTREACH_API_NOT_IMPLEMENTED`。

链路：

`POST /api/outreach/:opportunity_id`
`→ Session trusted principal`
`→ tenant-private profile + shared VERIFIED public facts`
`→ locked outreach input`
`→ input SHA-256 cache lookup`
`→ shared Agnes global lease`
`→ agnes-2.5-flash 只选择受控策略/问题/定位 code + fact_id/profile path`
`→ 服务端校验`
`→ 服务端模板渲染中文话术`
`→ H5 Public View`

关键边界：

- 浏览器不能提交自由 prompt、tone、tenant 或 profile；v0.1 请求体只能为空或 `{}`；
- 至少需要 VERIFIED `buyer_name` + `project_name`，否则409 fail-closed；
- Agnes **不直接写客户可见采购事实或自由销售文案**；只选择 allowlisted code/reference；
- 未知 fact_id、未知 profile path、缺失核心 fact 引用、越权定位全部拒绝；
- 最终客户可见中文话术由服务器只根据已验证事实和客户确认资源渲染；
- 明确带“不是医院官方表述、不代表中标概率或采购承诺”的声明；
- `requires_human_confirmation=true`；
- 相同 tenant/profile/opportunity 在 locked facts/context 不变时按 input SHA-256 缓存，重复点击不重复调用模型；
- outreach 与 Today Actions 共用同一个 Agnes global lease 状态，继续受 <=12 starts/60s、>=5s spacing、max in-flight=2 约束；
- on-demand outreach 使用 `INTERACTIVE_DEEP_DIVE` 最高交互优先级；
- 服务端从 `MCAI_AGNES_API_KEY` 读取 Key；可选 `MCAI_AGNES_BASE_URL` 仍必须通过官方 Agnes host allowlist；
- Key 缺失不会阻止 Pilot 其他功能启动，只有 outreach 返回503；
- API Key 不提交 GitHub、不进入 SQLite、不进入 H5/Public View。

H5 API 模式新增 `GroundedApiTodayActionsService.ts`；Mock 仍使用现有本地演示话术。

## Collector 自动持久化

已实现：

`抓取 → 解析 → VERIFIED event/facts → public event ledger → lifecycle 重算 → 当前 factual projection → product taxonomy → institution enrichment → today_repo`

关键正确性边界：

- 旧 TENDER 晚到不会把 AWARD 回退；
- 同日低精度冲突保持 `CONFLICTED/UNKNOWN`；
- taxonomy / award items / rental 只使用 current lifecycle event 的 VERIFIED facts；
- “采购”不自动等于“非租赁”；没有明确证据保持 UNKNOWN。

## Discovery：2/7 已可自动运行

DISCOVERY_READY：

1. `tjmugh_procurement`
2. `tj_first_central_hospital_procurement`

DISCOVERY_NOT_READY：

- `tj_government_procurement`：native list route 未解决；
- `tj_government_procurement_center`：采购公告 list classId/pagination 未解决；
- `ccgp_local_notices`：canonical list 是全国地方公告，不能直接当天津列表；
- `ccgp_procurement_intent`：搜索 CAPTCHA / query contract 未固定；
- `tj_public_resource_exchange`：结果列表 discovery contract 未固定。

`discovery_runtime.py` 已做 detail URL 持久化、成功24h重检、失败15→30→60…最大240分钟；`discovery_scheduler.py` 已接 Asia/Shanghai cadence、稳定 minute offset、强刷窗口及 `(source_id, slot_id)` 原子 claim。当前仍是 minute-granular，sub-minute jitter 未执行。

## CI / Build

为了兼容现有测试中的相对导入与绝对导入，已新增 `tools/__init__.py`，并把 CI unittest discovery 改为：

```text
python -m unittest discover -s tools/medical_pilot -t . -p "test_*.py" -v
```

这个修复**尚未得到执行证据**。

最新检查：HEAD `e9e501dd48074031186fc5efabbc2fb02629d714`，PR Run `33299581876`：

- `web-build` Job `99225035451`：`runner_id=0 / steps=[] / failure`
- `python-pilot` Job `99225035574`：`runner_id=0 / steps=[] / failure`

因此仍然没有执行 compileall、75组 unittest、JSON validation、npm install、TypeScript typecheck 或 H5 build。所有新增测试都只能标“已写入”，不能标 PASS；当前 failure 仍是 runner 未分配，不是代码 assertion/build failure。

## Agnes

Pilot 固定：

- `agnes-2.5-flash`
- <=12 starts / 60s
- start spacing >=5s
- max in-flight=2
- 0–2s stable jitter
- Provider start 前必须获得 global lease

API Key、真实模型路由、Provider 地址只属于服务端，不进入 H5/Public View。

## 天津政府采购 / Attachment

精确医疗附件入口仍是：

`TGPC-2025-A-0164` → `https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=cehQ4qF6Unc%2A&method=downEnId`

必须保持：`URL confirmed != bytes confirmed`。当前医疗真实附件 bytes 仍为0。

TJGPC `W008` 已确认是网上应答帮助，禁止用于 procurement discovery；真正采购公告/结果 list classId 与 pagination 仍未可靠验证，继续禁止盲猜 W00x。

## 下一步

1. Runner 或等价可信执行环境恢复后，真实执行75组 deterministic tests + H5 typecheck/build；
2. 获得 deterministic 执行证据后，用服务端 Key 做 grounded outreach 真正 Agnes smoke，不把 Key 放入仓库；
3. 把已持久化 `remind_at` 接入 tenant-safe reminder delivery planner；
4. 在单机服务器真实运行 discovery tick 并记录 listing/detail latency；
5. 逐个解决剩余5个 Source discovery contract，不猜 classId/pagination、不绕 CAPTCHA；
6. 捕获已知 `downEnId` 医疗附件真实 bytes；
7. 运行28个 Agnes benchmark 后再用 latency/queue 证据调整 cadence；
8. H5 Pilot 验证后再决定微信原生小程序。
