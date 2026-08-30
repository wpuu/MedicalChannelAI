# MedicalChannelAI 当前状态

日期：2026-08-30  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION + TODAY_ACTIONS_TRUSTED_BACKEND + H5_WEB_BASELINE`  
生产就绪：**false**  
Draft PR：**#1（保持 Draft，不合并）**

## 当前真实规模

- 7 个运行时 P0 Source：4 `IMPLEMENTED`、3 `PARTIAL_IMPLEMENTATION`
- 50 条 VERIFIED 天津商机 regression fixture
- 15 条 Institution Evidence
- **36 份 Schema/合同**
- **58 组 deterministic unittest 模块已写入，尚未获得真实执行 PASS 证据**
- 真实官方附件 bytes=0；医疗附件 bytes=0
- 首条天津医疗附件精确官方 URL 已确认：`TGPC-2025-A-0164 / method=downEnId`，但 bytes/MIME/SHA 尚未取得
- Agnes benchmark 28 case，未执行
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`

## Today Actions 可信后端

当前服务端链：

`Fact/Match/Score → Today Actions internal → input SHA-256 → terminal result reuse → dispatch queue → global lease → Agnes Worker → grounded validation → terminal result → Public View`

已经具备：

- 最终 Today Action 最多5张；
- 只有最终卡片允许进入模型候选；
- 官方事实、Evidence、客户私有上下文、Priority、AI Decision 分离；
- 无 VERIFIED grounded fact 时阻止模型生成；
- 越权/无依据模型输出拒绝展示；
- immutable input task identity + terminal-result 幂等；
- SQLite dispatch queue / lease / result store 可用于单机 Pilot；
- 跨服务器共享原子 Store 仅在水平扩容前补，不阻塞天津 Pilot。

### API 应用边界

`tools/medical_pilot/today_actions_api.py`：

- `GET /today` 对应 `build_today_actions_api_response()`；
- `GET /opportunity/:id` 对应 `get_today_opportunity_api_response()`；
- tenant/profile ownership 服务端校验；
- Query Budget 限制候选读取；
- pending Agnes 任务只进入服务端队列；
- Public View 不允许内部模型编排数据外泄。

### HTTP transport core

新增 `tools/medical_pilot/today_actions_http.py`，作为框架无关的薄 HTTP 边界：

- 只接受 GET；
- `/today` 与 `/opportunity/:id`；
- 强制依赖 `TrustedPrincipalResolver`；
- tenant/profile **不能**直接从浏览器 query/header 当成可信身份；
- 默认不打开 permissive CORS，优先同源；
- `Cache-Control: no-store, private`；
- 内部异常只返回稳定错误码，不把 Provider/内部错误正文返回浏览器；
- `RepositoryTodayActionsApplication` 直接复用现有 Today Actions 应用层，不复制业务逻辑。

新增 `test_today_actions_http.py`，验证伪造 tenant/profile query/header 不会覆盖服务端 trusted principal、未认证请求不会进入应用层、非法 method/path 与内部错误均 fail-closed。

**现在仍不直接创建可公网访问的 Vercel endpoint。** 原因是仓库还没有正式的 session/auth resolver 与真实 tenant Repository 运行时绑定。在这两项固定前，裸露 tenant/profile 参数会制造越权风险。

## H5：正式 `web/`

第二轮 `main/grok`、`main/claude` 审核后已停止双版本，选择 Grok 第二版进入正式短目录：

`web/`

已完成：

- `/today` + `/opportunity/:id`；
- 手机/桌面响应式；
- Service 与 Mock 解耦；
- NOT_FIT、提醒、完整跟进状态、按需话术 Demo；
- 官方事实 / 我的资源 / AI 判断视觉分区；
- 医院与采购单位分开，不用 buyer 冒充 hospital；
- 客户画像保留 true / false / 未确认三态；
- `web/src/types/public.ts` 单独声明 H5-safe Public View；
- `web/src/services/ApiTodayActionsService.ts` 做真实 Public View → UI view model 受控适配；
- `VITE_API_BASE_URL` 有值时切真实 API，无值时继续 Mock Demo；
- API 模式跟进暂存在浏览器本地，不伪装成服务端保存；
- grounded outreach 正式接口未定义前，API 模式 fail-closed；
- 前端 defense-in-depth：若响应出现 `model_requests / model_input / task_payloads / lease / provider / api_key / task_id` 等内部字段，直接拒绝消费。

## CI / Build

`.github/workflows/medical-pilot-ci.yml` 已增加独立 `web-build` job：

- Node 22
- `npm ci`
- `npx tsc --noEmit`
- `npm run build`

并把 `web/**` 加入 workflow path trigger。

最新已核实 HEAD `75814fecb8c3e6b8fdbb7016759a17d87b1d5db0`，Run `33292624120` 同时创建：

- `web-build` Job `99206804337`：`runner_id=0 / steps=[] / failure`
- `python-pilot` Job `99206804410`：`runner_id=0 / steps=[] / failure`

因此这次同样**没有执行 npm install、TypeScript、H5 build 或 Python test**。不能把任何一个 job 解释成代码失败，也不能标 PASS。

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

## 采集与通知

探索、用户推送、Agnes 调用继续分三层错峰。

Source 相位：天津财政`:01`、天津采购中心`:04`、CCGP`:07`、总医院`:03`、一中心`:11`、采购意向`:05`、公共资源`:19`。强刷窗口 `07:31–07:43`、`12:46–12:58`，保留 jitter/退避/周末降频。

通知：08:10晨报；08:30–18:30高优先 VERIFIED 可即时；13:15增量；18:30后普通项目排次日晨报；仅真正紧急变化允许晚间例外。

## 天津政府采购 / Attachment

精确医疗附件入口：

`TGPC-2025-A-0164` → `https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=cehQ4qF6Unc%2A&method=downEnId`

必须保持：`URL confirmed != bytes confirmed`。当前医疗真实附件 bytes 仍为0。

TJGPC：

- `W008` 已确认是网上应答帮助，禁止用于 procurement discovery；
- 真正采购公告/结果 list classId 与 pagination 仍未可靠验证；
- 已停止盲猜 W00x，优先使用已验证 detail/index/mirror 证据链。

## 下一步

1. 固定 trusted session/auth resolver；
2. 固定真实 tenant Repository 运行时绑定；
3. 两项完成后再加极薄 Vercel/等价 Serverless adapter，不让浏览器自报 tenant/profile；
4. Runner 恢复后执行58组 deterministic tests + H5 typecheck/build；
5. 再冻结 tenant-safe follow-up API；在此之前保持 local-only；
6. 再冻结 grounded on-demand outreach API；
7. 捕获已知 `downEnId` 医疗附件真实 bytes；
8. 有 deterministic 执行证据后运行28个 Agnes benchmark；
9. H5 Pilot 验证后再决定微信原生小程序。
