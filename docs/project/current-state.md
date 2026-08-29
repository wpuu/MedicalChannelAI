# MedicalChannelAI 当前状态

日期：2026-08-29  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION_CORE_EARLY`  
生产就绪：**false**  
Draft PR：**#1**

## 当前真实规模

- 6 个运行时 P0 Source：4 IMPLEMENTED、2 PARTIAL_IMPLEMENTATION
- **50 条 VERIFIED 天津商机 regression fixture**
- 5 条真实官方附件声明；真实附件 binary capture = 0
- **15 条天津机构官方 Evidence fixture**
- **23 份正式 JSON Schema/合同**
- **39 组 deterministic unittest 模块**
- 2 套 Agnes benchmark，共 **28 case**，均未执行
- Coverage：`PARTIAL / NOT_EXHAUSTIVE`
- `production_ready=false`

## 当前核心链路

`Source → Snapshot/SHA → Evidence Fact → Lifecycle/Identity → VERIFIED Material Event → Institution/Taxonomy → Profile Gate → Match → Query Budget → Priority → Daily Recommendation → Subscription Prefilter/Batch → Notification Route → Delivery State → Latency Ledger → Follow-up → Grounded Model Decision`

## Query Budget

客户画像可以很宽；限制的是单次执行，不要求客户为了性能填写虚假的小范围。

交互默认：DB候选500 → deterministic match200 → deep enrichment30 → model candidates10 → final action cards5；interactive live crawl=0；单商机模型默认最多24条 VERIFIED facts / 12000字符。

`NORMAL <=24 cells`；`WIDE 25..120`；`VERY_WIDE >120`。宽画像收紧深挖与模型 Top-N，不做 `地区 × 产品 × 数据源` 实时笛卡尔爬取。

## Daily / Continuous Subscription

订阅由客户画像驱动，不要求维护大量关键词：

1. 新 VERIFIED Material Event 进入；
2. `region + taxonomy + customer_type` 反向预筛；
3. 大量客户按 `batch_limit<=1000 + next_offset` 分批；
4. 每个候选仍跑完整 Match Gate；
5. 缺关键事实 → enrichment only；
6. 普通匹配 → daily digest；
7. fully-confirmed profile + 高优先级 → immediate；
8. 同 profile/opportunity/material-event 使用稳定 dedupe key；
9. terminal follow-up 默认抑制同一 opportunity 重复通知；有 owner 优先路由 owner。

## VERIFIED Material Event

新增：

- `medical-material-event.schema.json`
- `material_event.py`
- `test_material_event.py`

只有 VERIFIED opportunity + VERIFIED/non-model `OFFICIAL_PUBLIC_FACT` 才能生成 Material Event。`change_fields` 每个字段值必须逐项被 supplied fact 支持。

Material Event 身份按 **canonical opportunity + event type + normalized semantic change fields** 计算；官方镜像后来补 Evidence、发现时间变化、发布时间精度从 DAY 提升到 MINUTE，都不会制造第二个业务事件。

持久化 Event 在进入订阅服务前重新计算 hash/idempotency key；被篡改的 change fields 会 fail-closed。

## Notification Delivery State

新增：

- `medical-notification-delivery.schema.json`
- `notification_delivery.py`
- `test_notification_delivery.py`

同一 `subscription_dedupe_key + channel` 生成稳定 notification/idempotency identity。

状态：`QUEUED → SENT → DELIVERED`，或 `QUEUED/SENT → FAILED`；SUPPRESSED 使用真实 `audience=NONE`。重试复用同一 notification identity，默认最多3次；未获得 provider SENT ack 就失败的尝试同样消耗 retry slot。

queued/sent/failed/delivered 时间必须 timezone-aware 且顺序真实，不能生成脏 Latency Ledger。

## Latency Ledger

记录：`official published → discovered → fetched → verified → matched → notification queued → delivered`。

DAY 精度发布时间禁止伪造成分钟级同步速度；MINUTE/SECOND 才能计算 publication-to-discovery。阶段时间必须单调。

## Tianjin Government Procurement PRIMARY

继续 `PARTIAL_IMPLEMENTATION`，但 host 认识进一步收紧：

- `tjgp.cz.tj.gov.cn`
- `ccgp-tianjin.gov.cn`
- `www.ccgp-tianjin.gov.cn`

当前把这些视作**同一个 PRIMARY Source 的官方 host/alias**，不是多个来源、不会重复计商机。

2026 天津商业大学官方采购通知直接引用 `www.ccgp-tianjin.gov.cn/portal/documentView.do?...` 原文；同期采购公告仍引用 `tjgp.cz.tj.gov.cn` 业务入口。因此 Runtime 对两个 host 采用同一严格 detail validator：path 必须 `/portal/documentView.do`，query 必须恰好 `method=view + numeric id + ver=2`，参数顺序不限，多余/重复参数拒绝。

仍未验证：2026 原生列表/搜索/分页、crawler runtime 直接详情抓取、source-native attachment href、原生分钟级发布时间。因此**不升级 IMPLEMENTED**。

当前执行容器对两个 host 的直接网络探测都出现 DNS resolution failure；该结果只记录为执行环境限制，不能解释为网站 outage。

## Institution / Taxonomy / Agnes

15条 VERIFIED 官方 Institution Evidence；只做精确名称/显式 alias。

正式匹配使用稳定 taxonomy_ids。deterministic/human-confirmed classifier 已准入；Agnes taxonomy classifier 仍 `BENCHMARK_PENDING / can_drive_matching=false`。

50条 corpus audit harness 已就绪，但 Runner 未执行，因此不宣称 deterministic coverage rate。Agnes 两套 benchmark 共28 case，均未执行。

## Attachment

DOCX/XLSX parser 已实现；PDF Docling backend 只有代码合同。真实官方附件 bytes 捕获仍为0，因此不能宣称真实附件 parser 已验证。

## CI真实状态

最新确认 Medical Pilot CI Run `33228983861` / Job `99038171385`：conclusion=failure，`steps=null`。Python compile/unittest 没有开始执行。

因此当前39组 tests 只能标“已写入等待真实执行证据”，不能标 PASS，也不能解释为 assertion failure。Issue #2 持续跟踪。

## 下一步

1. 继续验证 `ccgp-tianjin.gov.cn` / `tjgp.cz.tj.gov.cn` 的当前原生列表/搜索/分页与附件 href，不猜接口。
2. 获取第一份真实天津医疗 DOCX/PDF bytes，跑 Snapshot/SHA/parser locator 全链。
3. 将 Material Event / Subscription / Delivery / Latency 接入后续持久化 Fact API / event scheduler。
4. Runner恢复后执行39组 tests 与 taxonomy corpus audit，优先修真实失败。
5. deterministic execution 有证据后再跑 Agnes benchmark。
6. 后端 API 稳定后再进入 H5/微信小程序端。
