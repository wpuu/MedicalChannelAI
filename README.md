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

- 当前单用户候选为 `fix/tjmugh-verification-20261002` / 草稿 [PR #75](https://github.com/wpuu/MedicalChannelAI/pull/75)，分支 `deploymentEnabled=false`。
- 每天两条独立每日 Cron：北京时间名义 08:20 / 12:20，Hobby 小时级精度；日期与明确时段识别周期，同周期幂等，自动 15 分钟增量链关闭，不升级套餐。
- 保留现有 `medicalchannelai-refresh-v2` Queue 和 v2 canonical；新消息版本门禁隔离旧积压，完整覆盖、失败旧数据、canonical/缓存和 AI 版本保护继续生效。
- 缓存长暂停后丢失完整 canonical 会阻断发布；发布前还要求完整已发布基线的每条机会仍有 canonical 历史。缺少既有来源记录或只有Top-N卡片时拒绝发布，不用旧种子或固定快照伪造自动更新。实际生产仍为旧主线 `6229959`；本候选未发布，不能宣称每天两次已恢复。
- 线上控制面、canonical 恢复及一次发布/回退门禁见 [受控恢复清单](docs/ops/twice-daily-release-20261003.md)。实际套餐、Cron、消费者、在途和延迟重试仍需核验。

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

CI（`verify.yml`）在代码 PR 上默认完整验证；仅显式 `[fast-verify]` 标记选择快速检查。文档更新受 paths-ignore 限制，不能把旧 HEAD 的绿灯当作新代码验证。
