# MedicalChannelAI

医疗渠道经营 AI / Medical Channel Intelligence。

本仓库用于独立开发医疗器械、IVD、耗材等医疗渠道商业情报与销售 Agent。首个 Pilot 为天津区域，目标是在**不允许模型创造采购事实**的前提下，把公开采购、采购意向、市场调研、院内比选、中标结果等信息转化为可追溯的商机、生命周期和销售行动建议。

## 当前状态

- 阶段：天津 Pilot v0.1 / M1 事实流水线迁移
- `production_ready=false`
- 首要原则：Evidence first；医院、项目、预算、日期、状态、中标单位、品牌型号等关键事实必须可追溯到原始来源
- 默认低成本模型候选：`agnes-2.5-flash`，仅承担分类、匹配、追问、解释和建议，不得成为官方事实权威
- 未来可通过受控 Skill / Tool API 接入 Hermes，但本仓库独立于 Hermes 产品代码

## 商业产品方向

- 当前公开试用继续以可追溯采购事实和可行动商机为核心，不因商业 V2 设计延迟上线。
- 上线后的核心优化方向是从“公开标讯 + AI”继续前移到**需求萌芽、医院事件时间线、装机后生命周期、医院配置缺口推测、渠道战斗力和持续销售监控**。
- 商业验证北极星新增“有效惊喜率”：用户看到的推荐中，有多少是“以前不知道，并且愿意进一步调查/联系”的机会。
- 完整产品商业补充见 [`docs/project/COMMERCIAL_OPPORTUNITY_V2.md`](docs/project/COMMERCIAL_OPPORTUNITY_V2.md)。

## Collector 执行面

- 当前生产候选使用单一 Vercel Daily Cron 启动 `medicalchannelai-refresh-v2` Queue。
- Collector canonical state、notice events、watch state、active cycle 与 latest verified snapshot 使用隔离的 Runtime Cache `:v2` namespace。
- Queue worker 在每个 stage 执行前校验 active `cycle_id`；旧 deployment / 旧 cycle 的延迟重试不得写入新的 v2 执行状态。
- verified snapshot 读取层仅允许经过完整 public snapshot validation 的 v1 → v2 一次性迁移；抓取失败不得覆盖最后一份已验证 snapshot。

开发状态、验收条件和当前工作以仓库内 `docs/project/` 与机器可读 checkpoint 为准。
