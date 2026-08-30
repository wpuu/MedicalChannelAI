# Grok 4.6 — MedicalChannelAI Today Actions H5 v0.1 生成提示词

> 用途：在 Arena/Grok 4.6 生成第一版可运行 H5 mock 前端。  
> 本文件只定义前端。**禁止 Grok 自行发明后端业务规则、模型逻辑、真实医疗事实或接口。**

---

请生成一个完整、可直接运行和继续开发的 H5 Web 前端项目。

## 项目名称

MedicalChannelAI / 医疗商机助手

核心产品定位：

> 每天告诉医疗厂家、经销商和渠道销售负责人，哪些医院商机现在最值得联系，以及为什么。

它不是普通“招标信息搜索网站”，首页重点必须是“今天该做什么”。

## 技术栈

必须使用：

- React 18+
- TypeScript
- Vite
- Tailwind CSS
- React Router
- Lucide React icons

输出一个完整项目，建议目录：

`frontend/h5-pilot/`

必须包含 `package.json`、Vite配置、Tailwind配置、TypeScript配置、`src/`、README 和可直接 `npm install && npm run dev` 的代码。

不要引入沉重UI框架；不要依赖后端才能启动。

## 只做两个页面

### 1. `/today`

Today Actions 首页，最多展示5张重点行动卡。

顶部显示：

- MedicalChannelAI / 医疗商机助手
- 当前日期
- “演示数据”明显标记
- 数据覆盖提示：`当前公开数据覆盖非穷尽，仅作为销售决策辅助`

概览区显示：

- 今日候选数
- 匹配商机数
- 今日重点数
- AI待分析数

每张行动卡必须首屏显示：

- rank
- 经营优先级分数，例如 86/100
- 固定提示：`经营优先级，不是中标概率`
- 医院/采购单位
- 项目名称
- lifecycle stage
- 预算（没有则显示“暂无公开信息”）
- 截止时间或预计采购时间（没有不得猜）
- VERIFIED / PARTIAL 等状态
- 匹配产品能力
- 客户已确认的医院关系；没有则显示“未确认关系”
- AI行动建议状态
- READY时展示动作、原因、风险
- AWAITING_MODEL时显示“AI分析排队中”
- BLOCKED_GROUNDING时显示“公开依据不足，暂不生成AI建议”
- MODEL_OUTPUT_REJECTED时显示“AI输出未通过事实校验”
- NOT_ELIGIBLE时显示“当前不需要AI建议”
- “查看详情”
- “查看官方依据”

操作按钮：

- 已联系
- 继续跟进
- 不适合
- 稍后提醒
- 生成沟通话术

这些操作在首版只能使用本地 mock state，并显著提示“演示操作，尚未保存到服务器”。

“生成沟通话术”只打开占位弹窗，不能真的调用AI，也不能预生成5张卡的话术。

### 2. `/opportunity/:id`

按清晰区块展示：

A. 官方事实
- 项目编号
- 项目名
- 采购单位/医院
- 科室
- 地区
- 生命周期
- 发布日期
- 截止日期
- 预计采购时间
- 预算
- 采购方式
- 产品/设备
- 公开联系人

任何缺失字段显示：`暂无公开信息`，绝对不能自己补。

B. 官方依据
- 展示 `evidence_source_urls`
- 每个URL按钮文案：`打开官方来源`

C. 我的资源
明显标记：`客户自有信息，不是官方公告`
- 医院关系
- 科室关系
- 关系强度
- 内部负责人
- 匹配产品能力
- 可找厂家
- 可合作渠道
- 是否可做租赁

D. 为什么排在前面
显示 Priority components，例如：
- 产品执行能力
- 医院关系
- 介入阶段
- 项目金额

必须固定显示：
`该分数用于安排销售资源优先级，不代表中标概率。`

E. AI行动建议
AI区域和官方事实区域必须视觉明显不同，标题注明：`AI经营建议`。
不得暗示AI建议属于官方公告。

F. 跟进记录
前端本地可切换：
- NEW
- REVIEWING
- CONTACTED
- RELATIONSHIP_VERIFIED
- PREPARING
- BID_SUBMITTED
- WON
- LOST
- NOT_FIT
- MONITOR
- ARCHIVED

选择 NOT_FIT 时弹出原因：
- 没有这个产品
- 找不到厂家
- 医院关系弱
- 项目金额太小
- 阶段太晚
- 不做该科室
- 不做该区域
- 不做租赁
- 竞品已锁定
- 其他

只保存前端 mock state，不能自动修改客户画像。

## 数据边界——必须严格执行

浏览器只允许使用 **Today Actions Public View**。

前端数据类型可以包含：

- schema_version
- mode
- input_candidate_count
- matched_count
- card_count
- model_request_count（只有数量）
- coverage_warning
- cards

Card可以包含：

- rank
- opportunity_id
- facts
- evidence_source_urls
- customer_context
- priority
- match_status
- recommendation_mode
- model_decision_status
- model_block_reason
- decision

### 绝对禁止在前端类型、mock、localStorage、日志或UI中出现

- model_requests
- model_input
- system prompt
- Agnes
- 模型供应商名称
- API Key
- Authorization token
- 上游API地址
- task_id
- lease_id
- internal dispatch
- classifier prompt
- 爬虫内部信息

不要为了“看起来完整”自己增加这些字段。

## Mock Service

必须实现统一接口，例如：

```ts
interface TodayActionsService {
  getTodayActions(): Promise<TodayActionsPublicResponse>;
  getOpportunity(id: string): Promise<TodayActionCard | null>;
  updateFollowup(id: string, input: FollowupInput): Promise<void>;
  requestOutreachDraft(id: string): Promise<OutreachDraft>;
}
```

第一版实现：`MockTodayActionsService`。

以后真实API上线时，只替换 Service 实现，不重写页面组件。

不要把评分、匹配、AI判断写进浏览器 Service。

## Mock 数据

生成最多5条**明显标记为演示数据**的天津医疗商机。

为了验证UI，至少包含以下不同状态：

1. READY
2. AWAITING_MODEL
3. BLOCKED_GROUNDING
4. MODEL_OUTPUT_REJECTED
5. READY 或 NOT_ELIGIBLE

Mock字段可以使用虚构/泛化数据，但必须在页面顶部和README明确写：

`本原型数据仅用于界面演示，不代表真实医院采购事实。`

不要把虚构内容包装成真实天津医院公告。

## 视觉要求

风格：专业B2B医疗销售工具。

- 白色/浅灰背景
- 信息密度中等
- 不做AI霓虹、赛博朋克、大面积渐变
- 状态色用于：优先级、风险、生命周期、VERIFIED状态
- 手机375px无横向滚动
- 桌面1440px内容区不要铺满全屏，建议 max-width 1200px 左右
- 卡片清晰、有层级
- 数字和状态易扫读
- 最突出的是“今天该做什么”，不是“抓了多少数据”

## 必须有的通用组件

建议拆分：

- AppShell
- CoverageBanner
- SummaryStats
- TodayActionCard
- PriorityScore
- LifecycleBadge
- VerificationBadge
- ModelDecisionPanel
- EvidenceLinks
- CustomerContextPanel
- PriorityBreakdown
- FollowupStatus
- NotFitDialog
- OutreachDraftDialog
- EmptyValue

不要做一个2000行单文件组件。

## 安全与可信UI

- VERIFIED官方事实、CUSTOMER_PRIVATE_FACTS、AI经营建议必须视觉分区。
- AI建议不能改写官方事实。
- 缺字段必须显示“暂无公开信息”。
- 所有外部Evidence链接用 `target=_blank` + `rel=noopener noreferrer`。
- 不使用 `dangerouslySetInnerHTML`。
- 不把URL参数直接渲染为HTML。

## 首版不要做

- 登录/注册
- 会员支付
- 全国地图
- 大量标讯瀑布流
- 复杂权限
- 原生微信小程序代码
- 后端数据库
- 爬虫
- Agnes/API调用
- 自动发送微信/短信
- 自动生成联系人
- 中标概率
- 自动批量生成沟通话术

## README必须说明

1. 安装和启动方法；
2. 当前是 H5 mock prototype；
3. 数据是演示数据；
4. 真实后端将来通过替换 `TodayActionsService` 接入；
5. 浏览器绝不能接触 model input / Provider / API Key；
6. `priority score != win probability`；
7. Coverage PARTIAL 时不能宣传全量覆盖。

## 最终验收

请生成的项目自行满足：

- `/today` 正常打开；
- `/opportunity/:id` 正常打开；
- 375px和1440px布局正常；
- 最多5张卡；
- READY/AWAITING/BLOCKED/REJECTED状态都可见；
- Evidence链接可点；
- 官方事实/客户私有信息/AI建议明显分区；
- 页面没有 model/provider/key/task/lease 字段；
- TypeScript无明显类型错误；
- 没有后端业务逻辑；
- 没有把mock宣传成真实采购信息。

请直接输出完整项目代码，不要只给设计稿或伪代码。
