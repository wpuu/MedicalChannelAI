# MCAI-DEMO-AVAIL-001 · 演示站可用性 P0

DATE=2026-09-27T21:22:00+08:00  
UPDATED=2026-09-27T23:14:00+08:00  
MODEL=GPT-5.6 Sol High  
SEVERITY=P0  
STATUS=MITIGATED

## 事件

2026-09-27 用户在给老杨现场演示时：

- https://medicalchannelai.vercel.app 无法打开；
- https://medicalai.qd.je 也无法打开。

现场演示失败，因此“公开演示入口可用”提升为产品发布前置门槛。

## 已确认事实

### Vercel 正式入口

当前零持续服务器成本的正式演示入口为：

- https://medicalchannelai.vercel.app
- https://medicalchannelai.vercel.app/today
- https://medicalchannelai.vercel.app/api/status

2026-09-27 复验：

- Production 已运行已接受版本；
- `/api/status` 返回 HTTP 200；
- `ready=true`；
- `degraded=false`；
- 数据源为 `DATABASE`；
- 快照为 `FRESH`；
- AI 配置可用；
- 前端不再错误显示“无法确认公开商机快照状态”。

### qd.je 入口退役

`medicalai.qd.je` 不再作为 Production 必须入口。

原因：

1. `qd.je` 当前未被 Public Suffix List 正确识别；
2. Vercel 因此要求无法由该子域持有人完成的上级域验证；
3. 原有方案通过 `35.211.124.40` 做跳转/代理；
4. 用户已确认该 GCP 资源产生接近 3 美元费用；
5. 为一个免费域名保留常驻付费 VPS 不符合本项目低成本原则。

因此：

- 停止继续修 `medicalai.qd.je -> Vercel Custom Domain`；
- 停止用常驻 VPS 为 qd.je 做反向代理或跳转；
- qd.je 不再进入自动 smoke 的成功条件；
- 未来若需要免费自定义域名，仅考虑已进入 PSL 且可直接绑定 Vercel 的后缀，例如 `qzz.io` / `dpdns.org`；
- 自定义域名迁移是后续优化，不阻塞当前线上演示入口。

## 当前 P0 关闭条件

以下条件需要满足：

1. `medicalchannelai.vercel.app` Production 版本与明确接受的 GitHub release commit 对齐；
2. `/`、`/today`、`/api/status` 在公开网络通过；
3. `/api/status.ready=true`；
4. 至少做一次中国现场网络（天津移动/联通/电信或真实手机流量）验证；
5. 保留一个不依赖实时在线站点的演示兜底；
6. 演示前 smoke check 成为固定动作。

不再要求：

- `medicalai.qd.je` 必须 Verified；
- 为 qd.je 保留任何常驻付费服务器。

## 自动检查

`.github/workflows/public-demo-smoke.yml` 只检查当前 canonical Production：

- `https://medicalchannelai.vercel.app/`
- `https://medicalchannelai.vercel.app/today`
- `https://medicalchannelai.vercel.app/api/status`
- HTTP 成功；
- `status.ready=true`。

这样避免已经退役的 qd.je/VPS 路线继续制造假告警。

## 后续自定义域名原则

如果后续仍需要更短、更像正式产品的公开域名：

- 优先 `qzz.io` / `dpdns.org` 等 PSL 已支持的免费后缀；
- 必须直接绑定 Vercel；
- 不新增常驻 VPS；
- 不为了免费域名引入新的持续账单；
- 在切换前，`medicalchannelai.vercel.app` 始终保留为稳定 fallback。

## GCP 止损

`35.211.124.40` 不再属于 MedicalChannelAI 的运行架构。

如果对应 VM / 外部 IPv4 仅用于本项目，应在 GCP 中停止并删除对应计算资源，并确认未保留会继续计费的静态外部 IPv4。

删除 DNS A 记录本身不能停止 GCP 账单；必须释放实际计费资源。

## 不做的事

- 不再围绕 qd.je 做 Vercel Verification 反复尝试；
- 不再用付费 VPS 给免费域名做转发；
- 不把另一个 `*.vercel.app` Preview 当独立备用站；
- 不把海外探针成功等价为天津现场可达。
