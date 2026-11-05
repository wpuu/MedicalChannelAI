# P0 Preview 验收记录

更新：2026-11-06（Asia/Shanghai）。用户本轮明确授权「仅部署 Preview 并运行验收，保持 Production 不变」。

## 结论与范围

最终部署的受控 HTTP 与页面验收完成；真实执行面完成单源消费验证，完整采集发布与持续调度仍待验收，`production_ready=false`。本记录区分本地代码回归、受控状态测试和真实来源请求，不将其中一项代替其他项。

## 环境与隔离

- 分支：`codex/p0-reliability-contracts`；工作树：`/workspace/MedicalChannelAI-p0`。原工作树保持干净。
- 最终代码：`079fa2e26bb29ea9807ce6763118d8959efc3e68`。
- 最终 Preview：`dpl_CoT8dKET2N1dwrWKd5NCQQ9e1MTR`，<https://medicalchannelai-bi9frg0oq-rerisse7-1717s-projects.vercel.app>。明确创建 Preview，未设置 Production target。
- Neon 测试分支：`br-cold-tooth-a5clhljh`（`preview/p0-reliability-20261106`）。最终验收使用该分支中新建的空数据库 `mcai_p0_acceptance_final`；初轮使用 `mcai_p0_acceptance`。测试未连接主分支数据库。
- `DATABASE_URL` / `POSTGRES_URL`、发布 token、Cron secret 等配置仅限定该 Git 分支的 Preview。模型 key 为空；没有复制生产模型凭据。
- 项目部署保护保持开启；验收使用部署专属的一小时临时访问凭据，最终验收凭据已撤销，旧部署凭据接口确认已不存在。Preview 和独立测试库保留，正常访问需项目权限。内部请求使用官方 SDK 取得当前平台 OIDC token，凭据不进入日志或本文。
- 该 Git 分支关闭自动部署；每次 Preview 均显式创建，未合并、提升环境或更改域名、DNS、EdgeOne。

## 验收中新增修复

1. Preview collector 原先固定调用 Production 发布地址。现限定为当前 immutable Preview hostname，拒绝缺失、非法地址和已知生产别名，使用独立发布凭据。
2. 受保护 Preview 的 Python 内部请求只读环境变量，取不到请求 context 中的平台凭据，导致 health 自请求失败。现使用 `vercel.oidc.get_vercel_oidc_token_sync()`；不执行 CLI refresh 或额外取 token 请求，错误仅记安全原因码。中间部署 `002a2e7` 的内部 health 已实际返回 200、DATABASE 和可用状态。
3. Queue runtime 的公开快照保留官方 `region`，没有离线发布脚本注入的 `market_*` 字段；商机池因此漏掉天津卡，而 Today 可见。现两处共用地区识别：有效显式代码 → 官方地区 → 缺地区时的已登记来源前缀。未知地区保持空值，不默认归为天津。

## 已完成的独立证据

- 本地正常 `npm run build`：832 个 Python 测试、全部 JS 合约检查、TypeScript 与 Vite 构建通过；新增地区边界与真实 mapper/loader 回归通过；独立终审无阻塞。
- 初轮 `4174f28` / `dpl_4Zj3vitvhuJyUbxWV2rbgb2eh8qC`：受控 HTTP 41/41 通过。该数字只属于初轮部署，最终部署结果另记，不直接继承。
- 初轮浏览器：6 个页面 HTTP 200，无页面脚本异常；3 次 cache-only AI POST 被测试拦截器主动阻断，没有发到服务端，不能计为 AI 成功调用。
- 第二轮浏览器：本地关注、跟进和刷新保持通过；5 个手机页面在 390px 无横向溢出。直接 API 与实际 AI 按钮均返回 `AI_NOT_CONFIGURED`，按钮呈现友好降级提示。该阶段发现的地区漏卡已修复，并在最终部署复验通过。
- 中间部署 `002a2e7` / `dpl_4nyhZSFd6wXMUScit5tAhYgBrBEX`：天津总医院单源任务返回 202，Queue 实际消费，发现 1 候选、详情核验 1 成功、0 失败，pending/barrier 均为 0。`snapshot_refreshed=false`：其他来源 canonical 未齐备，没有以局部数据发布完整快照。这证明单次消费与保护行为，不证明完整来源发布或持续调度。

## 最终部署结果

最终部署 HTTP 共 45 项逻辑检查通过，其中 44 项首次通过，1 项经一次重试通过；全部绑定上述 `079fa2e` / `dpl_CoT8dKET2N1dwrWKd5NCQQ9e1MTR`，未直接继承初轮结果。

覆盖未授权及非法 schema 拒绝、真实数据库发布/提交确认与 `fresh` 读回、30 小时过期门禁、未知/过期来源拦截、同批其他健康来源的隔离、缓存 MISS、无模型配置降级、未知商机、跨站请求和伪造事实拒绝、未来/冲突/回退/超大版本不污染权威、完整空池及受保护的 Python→Node 内部 health 200。

超大包检查首次意外得到 HTTP 502；现有运行日志未提供可归因的应用异常，原因未确定。立即读回确认权威未变，同一请求仅重试一次后返回预期 `400 RUNTIME_SNAPSHOT_TOO_LARGE`，再次读回仍未变。保留原始失败及重试证据，不记作首次全通过；后续应观察请求可靠性。

- [最终 HTTP 检查及原始异常](validation/preview-2026-11-06/final-http.json)
- [超大包重试及权威未变证据](validation/preview-2026-11-06/oversized-retry.json)
- [中间部署真实单源 Queue 结果](validation/preview-2026-11-06/queue-status-v2.json)

最终浏览器复验 18 项通过：保留天津卡原始缺失的 `market_code`，默认天津、全部地区与吉林筛选在 Today/商机池均一致；本地关注→跟进→刷新保持；真实 AI 按钮 503 的友好反馈；5 个手机页面在 390px 无溢出。该阶段页面异常与失败请求均为 0，不覆盖前述接口测试中的 502。

空池另有 9 项通过：普通 `/api/public-snapshot` GET 精确返回已提交空版本（CDN HIT / Age 1），Today、商机池、采购意向跟进和跟进页均显示正确空态，不回填旧卡片。未使用响应 mock 或缓存绕过。该只读阶段拦截 1 次自动 AI POST；请求未抵达服务器，不能声称该阶段零失败请求或 AI 生成通过。

- [最终页面复验 18 项](validation/preview-2026-11-06/browser-phase3.json)
- [空池页面复验 9 项](validation/preview-2026-11-06/browser-empty.json)

采购意向跟进的正例状态流转未测：这组事实卡没有采购意向，仅验证该页面合法空态。

收尾已移除受控的14源 HEALTHY 时钟。人工 QA 快照 `2026-11-05T16:51:40.751996+00:00` 经发布确认、权威 `fresh` 读回、status 与内部 health 验证：DATABASE、2张官方事实卡、整体 `degraded=true`，仅总医院保留实际观测的单次扫描时间，其余13源 UNKNOWN。该扫描时钟说明扫描成功，不说明 Queue canonical 已发布；快照的 QA 字段明确记录人工测试发布。

- [最终服务状态与逐源健康读回](validation/preview-2026-11-06/final-state.json)
- [收尾普通浏览器读回 5 项](validation/preview-2026-11-06/browser-final-state.json)：普通 GET 首次即 CDN HIT / Age 1 返回最终版本；Today 明确显示“部分信息源刷新异常或尚未确认，当前商机覆盖可能不完整。”，无页面脚本异常。

## 数据和结论限制

- 测试健康、未知、单源过期、空池等状态时，来源扫描时钟是明确的受控输入。14 源 HEALTHY 的测试输出只证明门禁与状态计算正确，不证明 14 源真实恢复采集。
- 天津卡事实来自冻结的 2026-11-05 官方公告原文：<https://www.tjmugh.com.cn/system/2026/11/05/030368176.shtml>；保留 3 组原文产品及官方报名截止 `2026-11-09 17:00 +08:00`。另一卡为已有官方吉林公告，未捏造新的采购事实。
- 无真实模型 key；503 是正确降级，模型成功输出、事实约束及费用尚未通过实测。
- 全源完整采集与发布、新三源在线闭环、后续自动 tick、长时间故障恢复及国内 P95 仍未完成。Preview 手动 Queue 验收不等于 Production Cron 或默认分支工作流已经启用。
- 相关性/资格门禁、项目生命周期串联、Gold benchmark、客户交付和续费验证不在本轮通过范围。

## Production 对照

本轮只读复查仍为 `dpl_4LPKoTdusrvbExXuzbMKtnyiT86C`、提交 `3216fd940dabfa7714383b6436908f9b72ff8a9c`、READY、target=production；项目 SSO 仍为 `all_except_custom_domains`。未对 Production 进行部署、写数据或配置变更。

[最终部署边界对照](validation/preview-2026-11-06/deployment-boundary.json)记录最后核对时间 `2026-11-05T16:54:30.040Z`。
