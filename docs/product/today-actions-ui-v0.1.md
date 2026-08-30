# MedicalChannelAI — Today Actions H5 UI v0.1

状态：**FROZEN_FOR_FIRST_FRONTEND_PROTOTYPE**  
目标：天津医疗渠道 Pilot；优先服务医疗厂家/经销商销售负责人。  
定位：不是标讯列表，而是“今天最值得采取行动的医疗商机”。

## 1. 前端边界

首版 H5 **只消费后端 `medical-today-actions-public.schema.json` Public View**，不在浏览器自行做商机评分、事实推断、产品匹配或 AI 判断。

内部 `medical-today-actions.schema.json` 中的 `model_requests/model_input`、Agnes Dispatch、global lease、terminal result、Provider 路由与 API Key **全部是服务端内部数据，不得下发浏览器**。

四类可展示信息必须视觉上区分：

1. `facts`：官方/已验证公开事实；
2. `evidence_source_urls`：官方 Evidence 入口；
3. `customer_context`：客户自己的关系、产品能力、合作策略，属于 `CUSTOMER_PRIVATE_FACTS`；
4. `decision`：受控 AI 判断，不得显示成官方事实。

Coverage 为 PARTIAL 时必须保留“当前公开数据覆盖非穷尽”提示，不得使用“已覆盖天津全部项目”之类文案。

## 2. 首版页面

### 2.1 今日行动 `/today`

移动端优先，同时适配桌面浏览器。

顶部：

- 产品名：MedicalChannelAI / 医疗商机助手；
- 日期；
- 数据状态：最近刷新时间（前端可先用 mock）；
- Coverage 提示。

概览区：

- 今日候选数 `input_candidate_count`；
- 匹配商机数 `matched_count`；
- 今日重点 `card_count`；
- AI待分析 `model_request_count`（仅数量，不下发内部 model request）。

核心区域只展示最多5张 Today Action Card，按 `rank` 排序。

每张卡首屏必须显示：

- 优先级分数 `priority.score`，并注明“经营优先级，不是中标概率”；
- 医院/采购单位；
- 项目名称；
- 生命周期阶段；
- 预算；
- 截止日期或预计采购时间（有哪个显示哪个，没有不得猜）；
- VERIFIED / PARTIAL 等状态；
- 匹配产品能力摘要；
- 客户确认的医院关系摘要（没有则明确“未确认关系”）；
- AI建议动作；
- 1–3条原因；
- 风险提示；
- “查看官方依据”入口。

卡片操作：

- `查看详情`；
- `已联系`；
- `继续跟进`；
- `不适合`；
- `稍后提醒`；
- `生成沟通话术`。

首版原型中操作按钮可以使用本地状态/mock，不得伪造后端已保存成功。`生成沟通话术` 首版可打开 UI 占位弹窗，后续接按需模型接口；不要为所有5张卡预生成话术。

### 2.2 商机详情 `/opportunity/:id`

按以下区块展示：

#### A. 官方事实

来自 `facts`：项目编号、项目名、采购单位/医院、科室、区域、阶段、发布日期、报名/投标截止、预计采购时间、预算、采购方式、产品项目、公开联系人。

空字段显示“暂无公开信息”，不得自行补全。

#### B. 官方依据

列出 `evidence_source_urls`，按钮文案“打开官方来源”。

#### C. 我的资源

来自 `customer_context`，明显标记“客户自有信息，不是官方公告”：

- 关系医院；
- 对接科室；
- 关系强度；
- 内部负责人 owner；
- 匹配的产品能力；
- 可找厂家/可合作渠道/可做租赁策略。

#### D. 为什么排在前面

展示 `priority.components`。必须显示：

> 该分数用于安排销售资源优先级，不代表中标概率。

#### E. AI行动建议

根据 `model_decision_status`：

- `READY`：展示 `decision.action / reasons / risks`；
- `AWAITING_MODEL`：显示“AI分析排队中”；
- `BLOCKED_GROUNDING`：显示“公开依据不足，暂不生成AI建议”；
- `MODEL_OUTPUT_REJECTED`：显示“AI输出未通过事实校验”；
- `NOT_ELIGIBLE`：显示“当前不需要AI建议”。

不要展示模型名、Provider、API Key、上游地址、model_input、lease id、task id 或内部错误栈。

#### F. 跟进记录

首版 UI 预留：

- NEW；
- REVIEWING；
- CONTACTED；
- RELATIONSHIP_VERIFIED；
- PREPARING；
- BID_SUBMITTED；
- WON；
- LOST；
- NOT_FIT；
- MONITOR；
- ARCHIVED。

`NOT_FIT` 时提供原因选择，但不要自动修改客户画像。

## 3. 首版不做

- 全国地图大屏；
- 大量原始标讯瀑布流作为首页；
- 自动生成虚构联系人；
- “中标概率xx%”；
- 自动替客户发送微信/短信；
- 每条商机自动生成销售话术；
- 支付、会员、复杂权限；
- 微信小程序原生代码。

首版目标只是把天津 Pilot 的真实价值演示清楚。

## 4. 视觉要求

- B2B医疗销售工具，不做“AI霓虹科技风”；
- 清爽、专业、信息密度中等；
- 白/浅灰背景，状态色只用于优先级、风险、生命周期；
- 中文界面；
- 手机宽度 375px 时无需横向滚动；
- 桌面 1440px 时内容区不要铺满全屏；
- 卡片之间层级清晰；
- 重点突出“今天该做什么”，而不是“我们抓了多少数据”。

## 5. 前端技术栈

第一版原型建议：

- React 18+
- TypeScript
- Vite
- Tailwind CSS
- React Router
- Lucide icons

不需要后端框架。先使用本地 `src/data/today-actions.mock.ts`，所有 mock 页面显著标记“演示数据”。后续把 data service 换成真实 API，不重写 UI。

## 6. 前端数据接口

建议统一封装：

```ts
interface TodayActionsService {
  getTodayActions(): Promise<TodayActionsPublicResponse>;
  getOpportunity(id: string): Promise<TodayActionCard | null>;
  updateFollowup(id: string, input: FollowupInput): Promise<void>;
  requestOutreachDraft(id: string): Promise<OutreachDraft>;
}
```

首版 `MockTodayActionsService` 实现这些接口；真实 API 接入时只替换 service 实现。

服务端内部流程固定为：

`Fact/Match/Score → Today Actions internal → input fingerprint → terminal-result reuse → pending Agnes Dispatch/Lease/Worker → Today Actions Public View`

前端不参与其中任何一步。

## 7. 验收

第一版前台至少满足：

1. 首页最多5张重点行动卡；
2. 手机与桌面布局正常；
3. 官方事实、客户私有信息、AI判断视觉分区；
4. 事实缺失时不猜；
5. Evidence 可点击；
6. Priority 明示不是中标概率；
7. AI异常/阻断状态均有清晰 UI；
8. 跟进状态可在 mock 中交互；
9. “生成沟通话术”按需触发，不自动批量生成；
10. 浏览器看不到 model_input、Agnes/Provider/API Key/lease/task 等内部实现信息。
