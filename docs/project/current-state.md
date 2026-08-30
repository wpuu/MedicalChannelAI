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
- **57 组 deterministic unittest 模块已写入，尚未获得真实执行 PASS 证据**
- 真实官方附件 bytes=0；医疗附件 bytes=0
- 首条天津医疗附件精确官方 URL 已确认：`TGPC-2025-A-0164 / method=downEnId`，但 bytes/MIME/SHA 尚未取得
- Agnes benchmark 28 case，未执行
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`

## Today Actions 可信后端

当前服务端链：

`Fact/Match/Score → Today Actions internal → input SHA-256 → terminal result reuse → dispatch queue → global lease → Agnes Worker → grounded validation → terminal result → Public View`

已经具备：

- 最终 Today Action 最多 5 张；
- 只有最终卡片允许进入模型候选；
- 官方事实、Evidence、客户私有上下文、Priority、AI Decision 分离；
- 无 VERIFIED grounded fact 时阻止模型生成；
- 越权/无依据模型输出拒绝展示；
- immutable input task identity + terminal-result 幂等；
- SQLite dispatch queue / lease / result store 可用于单机 Pilot；
- 跨服务器共享原子 Store 仅在水平扩容前补，不阻塞天津 Pilot。

### API 应用边界

`tools/medical_pilot/today_actions_api.py` 已实现应用层边界：

- `GET /today` 对应 `build_today_actions_api_response()`；
- `GET /opportunity/:id` 对应 `get_today_opportunity_api_response()`；
- tenant/profile ownership 服务端校验；
- Query Budget 限制候选读取；
- pending Agnes 任务只进入服务端队列；
- Public View 明确禁止 `model_requests / model_input / task_payloads / dispatch / lease / Provider / API Key` 等内部编排信息。

当前仍缺的是把上述 Python 应用边界挂到实际 HTTP/Serverless transport，并完成真实部署联调。

## H5：正式选择 `web/`

第二轮分别生成了 `main/grok` 与 `main/claude` 两个候选。审核后停止双版本继续开发，选择 **Grok 第二版**作为正式底稿，已复制到开发分支短目录：

`web/`

候选目录仍保留在 main 作为参考，不继续修改。

### 已完成的前端收敛

- `/today` + `/opportunity/:id`；
- 手机/桌面响应式布局；
- Mock Service 与页面隔离；
- NOT_FIT、提醒、跟进状态、按需沟通话术 Demo；
- 官方事实 / 我的资源 / AI 判断视觉分区；
- 医院与采购单位分开，不用 buyer 冒充 hospital；
- 客户画像三态保留：`true / false / 未确认`，未知值不会自动解释成“不可以”；
- `web/src/types/public.ts` 单独声明后端 H5-safe Public View；
- `web/src/services/ApiTodayActionsService.ts` 负责真实 Public View → UI view model 的受控适配；
- 配置 `VITE_API_BASE_URL` 时使用真实 API；未配置时继续使用 Mock Demo；
- API 模式下跟进暂存在浏览器本地，不伪装成服务端保存；
- API 模式下真实沟通话术接口未定义前 fail-closed，不擅自本地伪造正式结果；
- 前端增加 defense-in-depth：若响应出现 `model_requests / model_input / task_payloads / lease / provider / api_key / task_id` 等内部字段，直接拒绝消费。

### H5 当前未完成

- `npm run build` **尚未获得本轮实际执行证据**；当前环境无法直接拉取私有仓库到本地执行，因此不能标 PASS；
- 真实 HTTP transport 尚未部署；
- 服务端跟进 API 尚未冻结，因此跟进继续 local-only；
- grounded on-demand outreach API 尚未冻结，因此正式 API 模式暂不生成话术。

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

必须继续保持：`URL confirmed != bytes confirmed`。当前医疗真实附件 bytes 仍为 0。

TJGPC：

- `W008` 已确认是网上应答帮助，禁止用于 procurement discovery；
- 真正采购公告/结果 list classId 与 pagination 仍未可靠验证；
- 已停止盲猜 W00x，优先使用已验证 detail/index/mirror 证据链。

## CI

此前多次 GitHub Actions 均出现 `runner_id=0 / steps=[]`，属于 runner 未分配，不是 Python assertion failure。57 组 deterministic tests 目前只能标记“已写入、待真实执行”。

H5 本轮也不得在没有 `npm run build` 实际执行证据前标 PASS。

## 下一步

1. 核实当前 `web/` HEAD 对应 GitHub Actions 是否仍为 runner-level 阻塞；
2. 增加薄 HTTP/Serverless transport，把现有 Today Actions API 应用边界真正暴露给 H5；
3. transport 可用后做 `/today`、`/opportunity/:id` 的真实 Public View 联调；
4. 再冻结 tenant-safe follow-up API；在此之前保持 local-only；
5. 再冻结 grounded on-demand outreach API；
6. Runner 恢复后执行57组 deterministic tests和 web build；
7. 捕获已知 `downEnId` 医疗附件真实 bytes；
8. 有 deterministic 执行证据后再运行28个 Agnes benchmark；
9. H5 Pilot 验证工作流后再决定微信原生小程序。
