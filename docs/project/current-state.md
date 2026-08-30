# MedicalChannelAI 当前状态

日期：2026-08-30  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION + TODAY_ACTIONS_TRUSTED_BACKEND + H5_AUTH_SINGLE_HOST_RUNTIME + PERSISTENT_DISCOVERY_INITIAL`  
生产就绪：**false**  
Draft PR：**#1（保持 Draft，不合并）**

## 当前真实规模

- 7 个运行时 P0 Source：4 `IMPLEMENTED`、3 `PARTIAL_IMPLEMENTATION`
- 50 条 VERIFIED 天津商机 regression fixture
- 15 条 Institution Evidence
- **36 份 Schema/合同**
- **69 组 deterministic unittest 模块已写入，尚未获得真实执行 PASS 证据**
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

单机 Pilot 已不再依赖浏览器自报 tenant/profile：

- `session_auth.py`：随机 opaque session，数据库只存 SHA-256；
- `invite_auth.py`：一次性高熵 invite，默认 30 分钟，成功兑换后不可重放；
- Cookie：`__Host-mcai_session; Secure; HttpOnly; SameSite=Strict`；
- `auth_http.py`：只允许 invite redeem / logout；
- `today_actions_http.py`：GET `/today`、`/opportunity/:id`，身份必须来自 trusted principal；
- `today_repo.py`：客户画像 tenant-private；公开采购事实跨客户共享，不复制；
- `today_runtime.py`：单 SQLite 文件绑定 repository/session/invite/Agnes queue/result；
- `pilot_api.py` + `pilot_server.py`：same-origin `/api/*` 参考入口，默认只监听 `127.0.0.1:8787`；
- `web/`：`/login` + `/today` + `/opportunity/:id`；真实 API 401 自动回登录；Mock 模式仍可独立演示。

当前禁止把这套 SQLite runtime 直接复制到多 VPS、多容器或无共享磁盘 Serverless；Vercel Function 本地文件系统也不能充当持久数据库。

## Collector 自动持久化

已新增：

- `collector_ingest.py`
- `collector_store.py`
- `cli.py --db`

单个已登记官方详情 URL 现在可以直接：

`抓取 → 解析 → VERIFIED event/facts → public event ledger → lifecycle 重算 → 当前 factual projection → product taxonomy → institution enrichment → today_repo`

关键正确性边界：

- 先抓 AWARD、后补抓旧 TENDER，lifecycle 不会倒退；
- 同日低精度冲突保持 `CONFLICTED/UNKNOWN`；
- 产品 taxonomy、award items、租赁判断只取 current lifecycle event 的 VERIFIED facts，旧 scope 不污染新结果；
- “采购”本身不自动等于“非租赁”；没有明确证据就保持 UNKNOWN；
- 天津财政三个已登记官方详情 host 现在与 registry/fetcher 一致，合法官方备用域名不会再被自身 host allowlist 拒绝。

## Discovery：2/7 已可自动运行

### DISCOVERY_READY

1. `tjmugh_procurement`
   - `https://www.tjmugh.com.cn/cgxxtzgg/index.shtml`
2. `tj_first_central_hospital_procurement`
   - `https://www.tj-fch.com/ywgk/ynbx/index.shtml`

两者都有专属天津医院 listing + 已实现 `discover()` + registry detail URL 校验。

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
- 成功 detail 默认 24h 内不重复抓；
- detail 失败 15→30→60…分钟退避，最多 240 分钟；
- detail URL 自己失败不会错误增加整个 listing Source 的失败次数。

`discovery_scheduler.py`：

- 直接复用 `discovery_cadence.tianjin.v0.1.json`；
- Asia/Shanghai；
- 总医院稳定 `:03`，一中心稳定 `:11`；
- 工作日白天 EARLY_SIGNAL 基线 15 分钟，周末/夜间降频；
- listing/source 级失败扩大 regular cadence，成功后清零；
- `07:31–07:43`、`12:46–12:58` 强刷窗口已接入；
- SQLite `PRIMARY KEY(source_id, slot_id)` 原子 claim，同一 host 上重复 cron、进程重启、重叠 tick 不会重复执行同一 slot；
- 推荐每分钟调用一次幂等 tick，而不是常驻死循环：

```text
python -m tools.medical_pilot.discovery_scheduler --db /srv/medical/pilot.sqlite
```

当前是 minute-granular scheduler；policy 中 10% sub-minute jitter 尚未实际执行，单机 Pilot 先依靠稳定 minute offsets 错峰。

## CI / Build

最新代码验证触发点：HEAD `ab844000bd0ba890d79d61db28dc58fe416253ed`，Run `33294369330`：

- `web-build` Job `99211395102`：`runner_id=0 / steps=[] / failure`
- `python-pilot` Job `99211395181`：`runner_id=0 / steps=[] / failure`

所以依然**没有执行 npm install、TypeScript、H5 build 或 Python tests**。69 个 test modules 是“已写入”，不是 PASS。两个 failure 仍只能解释为 runner 未分配，不能解释为代码 assertion/build failure。

## Agnes

Pilot 固定：

- `agnes-2.5-flash`
- <=12 starts / 60s
- start spacing >=5s
- max in-flight=2
- 0–2s stable jitter
- provider start 前必须获得 global lease
- terminal READY/REJECTED 按 immutable input 幂等复用

API Key、模型路由、Provider 地址均只属于服务端，不进入 H5/U盘/公开返回。

## 通知

通知策略保持：08:10 晨报；08:30–18:30 高优先 VERIFIED 可即时；13:15 增量；18:30 后普通项目排次日晨报；仅真正紧急变化允许晚间例外到 21:30。

Discovery 与通知窗口彼此独立：通知 quiet hour 不停止后台 discovery。

## 天津政府采购 / Attachment

精确医疗附件入口：

`TGPC-2025-A-0164` → `https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=cehQ4qF6Unc%2A&method=downEnId`

必须保持：`URL confirmed != bytes confirmed`。当前医疗真实附件 bytes 仍为0。

TJGPC：

- `W008` 已确认是网上应答帮助，禁止用于 procurement discovery；
- 真正采购公告/结果 list classId 与 pagination 仍未可靠验证；
- 已停止盲猜 W00x，优先使用已验证 detail/index/mirror 证据链。

## 下一步

1. Runner 或等价可信执行环境恢复后，真实执行69组 deterministic tests + H5 typecheck/build；
2. 获得执行证据后，在单机服务器用 cron/systemd timer 每分钟调用一次 discovery tick，并记录 listing/detail 延迟；
3. 逐个解决剩余5个 Source 的 discovery contract，禁止猜 classId/pagination、禁止绕 CAPTCHA；
4. 冻结并实现 tenant-safe 服务端 follow-up/reminder；当前 H5 继续 local-only；
5. 冻结 grounded on-demand outreach API；
6. 捕获已知 `downEnId` 医疗附件真实 bytes；
7. 有 deterministic 执行证据后运行28个 Agnes benchmark；
8. H5 Pilot 验证后再决定微信原生小程序。
