# MedicalChannelAI GCP 退役审计与接管状态

- 日期：2026-09-27
- 模型：GPT-5.6 Sol
- 项目：wpuu/MedicalChannelAI
- 目的：在不影响其他 GCP 服务的前提下，移除 MedicalChannelAI 对 GCP 的生产流量与任务执行依赖。

## 1. 已确认的 GCP 角色

MedicalChannelAI 在 GCP VM `instance-20260412-052405` 上没有发现独立业务数据库或长期业务代码副本。

项目专属角色只有：

1. GitHub Actions 自托管 Runner：`medicalchannelai-gcp-1`
2. Caddy 对 `medicalai.qd.je` 的网站转发

Runner 工作区约 9.9 MB，为 GitHub Actions 临时 checkout。

VM 同时运行与 MedicalChannelAI 无关的 LiteLLM/代理等服务，因此禁止删除整台 VM。

## 2. 已完成：停止 GCP 全量网站反代

原链路：

`medicalai.qd.je -> 35.211.124.40(GCP/Caddy) -> medicalchannelai.vercel.app`

2026-09-27 已将 Caddy 从 `reverse_proxy` 改为永久重定向：

`medicalai.qd.je -> 301/308 -> https://medicalchannelai.vercel.app{uri}`

已实际验收通过。旧域名仍经过 GCP 返回一个很小的重定向响应，但不再经 GCP 转发网站正文，因此已经显著降低此链路的 GCP 出网量。

## 3. DNS 当前状态

`medicalai.qd.je` 当前：

- A：`35.211.124.40`
- CNAME：无
- DNS 托管：DigitalPlat
- NS：`ns1.digitalplat.org` ～ `ns4.digitalplat.org`

最终应先在 Vercel 添加 `medicalai.qd.je` 为自定义域名，再按 Vercel 给出的 DNS 目标修改 DigitalPlat 记录。DNS 验收完成前保留 Caddy 重定向。

## 4. GCP Runner 仍不能停的原因

当前这些工作流仍依赖：

`self-hosted + linux + x64 + medicalchannelai-ci`

包括：

- Verify MedicalChannelAI
- Tianjin Medical Refresh
- Regional Medical Refresh

2026-09-27 已建立 Draft PR #24 尝试迁到 `ubuntu-latest`。

两次 GitHub-hosted 实际运行均在拿到 Runner 前失败：

- `runner_id=0`
- `steps=[]`
- 2～3 秒结束

因此这不是仓库测试代码失败，当前也不能把 GitHub-hosted Runner 当作已验证替代执行面。

PR #24 在该问题解决前禁止合并。

## 5. Vercel-native Collector 当前真实状态

生产端代码已经有：

- Vercel Cron
- Vercel Queue
- Runtime Cache
- 天津深度抓取链
- 天津日间增量抓取链

但生产实时检查显示：

- `CRON_SECRET` 未配置
- `/api/pipeline-health` 因此返回不可用
- Collector stage 全部为 0
- Vercel-native Collector 实际没有接管每日刷新

现有安全边界明确要求 Cron 使用 `Authorization: Bearer CRON_SECRET`，不得用可伪造的 Header 替代。

## 6. Vercel Collector 还缺区域市场覆盖

当前 Vercel 深度链只覆盖天津相关来源。

产品公开快照还包含：

- 北京
- 河北
- 辽宁
- 吉林
- 黑龙江

这些区域当前由 `.github/workflows/regional-medical-refresh.yml` 在 GCP Runner 上执行。

因此，即使只配置 `CRON_SECRET`，也不能立即关闭 GCP Runner；必须先把区域抓取迁进 Vercel Queue，或找到另一个已验证执行面。

## 7. Runtime Cache 不能继续充当权威持久快照

2026-09-26 GCP Runner 已成功：

- PUT 新快照到 `medicalchannelai.vercel.app/api/public-snapshot`
- 当场 round-trip 验证通过
- 快照时间：`2026-09-26T13:36:14.398671+08:00`
- pool：406

但 2026-09-27 生产重新读取时已经回退到：

- `2026-09-24T13:32:02.844764+08:00`
- runtime_origin：`BUNDLED`
- pool：372

说明“发布成功 + 立即回读成功”不能证明 Runtime Cache 是持久真源。

当前 `_verifiedSnapshot.js` 将 `PUBLISHED_RUNTIME_SNAPSHOT_KEY` 当成权威最新快照，这个假设需要废除。Runtime Cache 只能作为加速/短期运行状态。

## 8. 数据库基础设施代码已存在，但生产未配置

仓库已有 Postgres 数据层：

- `web/api/_privateDb.js`
- `web/api/_publicIntelligenceDb.js`
- `public_opportunities`
- `public_opportunity_versions`
- `public_snapshot_materializations`
- `public_ai_briefs`

但是生产 `/api/auth/me` 实测返回：

`PRIVATE_DATABASE_NOT_CONFIGURED`

说明当前 Production 没有 `DATABASE_URL` / `POSTGRES_URL`。

长期正确方向是把权威公开快照/机会状态放到持久数据库，Runtime Cache 仅作为缓存；但这要求先完成数据库环境连接。

## 9. GitHub Secret / Vercel 授权现状

历史授权工作流仍能读取当前 GitHub Secret `VERCEL_TOKEN`：

2026-09-27 重跑时 `Require deployment credential` 为 PASS。

GCP VM 本机没有可复用的 Vercel CLI 登录态。

因此 Vercel 控制面修改不能依赖 VM 本地登录。

## 10. 退役门槛

关闭/注销 `medicalchannelai-gcp-1` 前必须全部满足：

1. Vercel-native Collector 覆盖天津 + 五个区域市场；
2. Vercel Production 已配置并验证 Cron 鉴权；
3. 至少一次 Vercel Queue 深度周期完整成功；
4. 生产公开快照更新为该周期的新时间并保持可读；
5. 快照权威持久层不再依赖 Runtime Cache；
6. GitHub 验证工作有非 GCP 的可用替代执行面，或明确把验证与刷新拆分处理；
7. `medicalai.qd.je` DNS 已直接接入 Vercel；
8. DNS 生效后确认旧域名不再命中 `35.211.124.40`；
9. 只停 MedicalChannelAI Runner/专属 Caddy 配置，不删除 VM、不影响 LiteLLM/其他服务。

## 11. 下一工程步骤

下一步单独在新分支实现：

- Vercel Queue 区域抓取 stage；
- 区域记录进入统一 publish；
- 使 Vercel Collector 生成的完整快照可被生产读取；
- 保持现有 Cron fail-closed 鉴权不降低；
- 不在该分支直接关闭 GCP Runner。

完成 Preview + 自托管现有测试后，再做生产接管。
