# MedicalChannelAI

医疗渠道经营 AI / Medical Channel Intelligence。

本仓库用于独立开发医疗器械、IVD、耗材等医疗渠道商业情报与销售 Agent。首个 Pilot 为天津区域，目标是在**不允许模型创造采购事实**的前提下，把公开采购、采购意向、市场调研、院内比选、中标结果等信息转化为可追溯的商机、生命周期和销售行动建议。

## 当前状态

- 阶段：天津 Pilot v0.1 / M1 事实流水线迁移
- `production_ready=false`
- 首要原则：Evidence first；医院、项目、预算、日期、状态、中标单位、品牌型号等关键事实必须可追溯到原始来源
- 当前低成本模型：`agnes-3.0-flash`，仅承担分类、匹配、追问、解释和建议，不得成为官方事实权威
- 未来可通过受控 Skill / Tool API 接入 Hermes，但本仓库独立于 Hermes 产品代码

## Collector 执行面

- 当前生产候选使用单一 Vercel Daily Cron 启动 `medicalchannelai-refresh-v2` Queue。
- Collector canonical state、notice events、watch state、active cycle 与 latest verified snapshot 使用隔离的 Runtime Cache `:v2` namespace。
- Queue worker 在每个 stage 执行前校验 active `cycle_id`；旧 deployment / 旧 cycle 的延迟重试不得写入新的 v2 执行状态。
- verified snapshot 读取层仅允许经过完整 public snapshot validation 的 v1 → v2 一次性迁移；抓取失败不得覆盖最后一份已验证 snapshot。

开发状态、验收条件和当前工作以仓库内 `docs/project/` 与机器可读 checkpoint 为准。

## 仓库结构

| 路径 | 说明 |
|---|---|
| `web/` | 生产应用：Vite + React 前端（`src/`）、Vercel Serverless API（`api/`）、Python 采集器与数据流水线（`pipeline/`、`collector_*.py`） |
| `web/scripts/` | 构建前合约检查（`npm run build` 会通过 `run-prebuild.mjs` 全部执行） |
| `ops/` | 国内入口代理（EdgeOne）与域名跳转配置 |
| `docs/project/` | 当前项目状态、架构与 checkpoint（以此为准） |
| `docs/ops/` | 运维与故障记录 |
| `docs/archive/`、`archive/` | 历史记录与早期 UI 原型，不参与构建/部署 |

## 本地验证

```bash
cd web
npm ci
npm run build          # 全部 pipeline 单测 + JS 合约检查 + 构建
```

CI（`verify.yml`）在 PR 上默认只跑快速检查；head commit message 含 `[full-verify]` 时执行完整构建。
