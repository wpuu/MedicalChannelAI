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

- 基础草稿[PR #75](https://github.com/wpuu/MedicalChannelAI/pull/75)为`fix/tjmugh-verification-20261002`、a2131e4；三源离线实现草稿[PR #78](https://github.com/wpuu/MedicalChannelAI/pull/78)为`fix/twice-daily-source-parity-20261017`、产品c0d0215，叠加PR75。两分支`deploymentEnabled=false`，尚未合并/部署。
- PR75产品祖先`8b4b749bf057ed3f5a9b830fdef84ecc04bb1bd2`有[Verify 37117043888 SUCCESS](https://github.com/wpuu/MedicalChannelAI/actions/runs/37117043888)、879项Python及完整构建历史证据。PR78已有164项本地离线检查，完整新产品CI/独立审查未完成；祖先绿灯不转移给新代码。
- 候选每天两条独立每日Cron：北京名义08:20/12:20，Hobby小时级精度；日期与明确时段识别周期、同周期幂等，候选关闭自动15分钟链，不升级套餐。这不是实际线上Cron启用证明。
- 周期终点保留标记，由后续周期替换或TTL过期；已结束周期重投不执行，避免旧终点读后删除误删午间新标记。
- 保留现有 `medicalchannelai-refresh-v2` Queue 和 v2 canonical；新消息版本门禁隔离旧积压，完整覆盖、失败旧数据、canonical/缓存和 AI 版本保护继续生效。
- 缓存长暂停后丢失完整canonical会阻断发布；完整已发布基线的每条机会必须仍有canonical历史。缺历史或只有Top-N时拒绝发布，不用旧种子/固定快照伪造更新。10月17日实际生产已核对为`3216fd9`、READY `dpl_4LPKoTdusrvbExXuzbMKtnyiT86C`；DATABASE版本10月7日、437条、STALE/degraded，候选未上线。
- 三源仍history-only、22stage及partial/AI限制。经一次明确批准，[4页官方HTML已仅本地保存](docs/ops/official-html-20261017.md)；发现GB2312解码、真实列表结构及首页14条intent超过3条上限的问题。分页/30日覆盖、正式注册、目标平台和25stage接线仍未完成，历史保留不能称新监控。
- [最新只读核验与发布/回退门禁](docs/ops/release-readback-20261017.md)记录生产公开池缺4条历史intent、437条缺地区身份字段；PR75已有最小读取/投影修复，尚未上线。API按Hobby分类，但实际Cron、消费者、队列与完整canonical库存仍缺，当前不可发布、不能宣称每天两次恢复。

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
