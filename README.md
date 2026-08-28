# MedicalChannelAI

医疗渠道经营 AI / Medical Channel Intelligence。

本仓库用于独立开发医疗器械、IVD、耗材等医疗渠道商业情报与销售 Agent。首个 Pilot 为天津区域，目标是在**不允许模型创造采购事实**的前提下，把公开采购、采购意向、市场调研、院内比选、中标结果等信息转化为可追溯的商机、生命周期和销售行动建议。

## 当前状态

- 阶段：天津 Pilot v0.1 / M1 事实流水线迁移
- `production_ready=false`
- 首要原则：Evidence first；医院、项目、预算、日期、状态、中标单位、品牌型号等关键事实必须可追溯到原始来源
- 默认低成本模型候选：`agnes-2.5-flash`，仅承担分类、匹配、追问、解释和建议，不得成为官方事实权威
- 未来可通过受控 Skill / Tool API 接入 Hermes，但本仓库独立于 Hermes 产品代码

开发状态、验收条件和当前工作以仓库内 `docs/project/` 与机器可读 checkpoint 为准。
