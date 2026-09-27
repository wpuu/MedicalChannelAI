# MCAI-DEMO-AVAIL-001 · 演示站可用性 P0

DATE=2026-09-27T21:22:00+08:00  
MODEL=GPT-5.6 Sol High  
SEVERITY=P0  
STATUS=OPEN

## 事件

2026-09-27 用户在给老杨现场演示时：

- https://medicalchannelai.vercel.app 无法打开；
- https://medicalai.qd.je 也无法打开。

现场演示失败，因此“公开演示入口可用”提升为产品发布前置门槛。在本 P0 关闭前，不应把新增业务功能置于演示可用性之前。

## 2026-09-27 复核事实

### Vercel 正式入口

当前 Vercel 项目：

- Project: `medicalchannelai`
- Project ID: `prj_7fk44eKUhdbfTUaXxEBMgIzZiqUM`
- Production alias: `medicalchannelai.vercel.app`
- 当前 Production deployment: `dpl_6YPga6ronr8mmbtMnAFsG4ohXgz7`
- Production commit: `6ed4a1fa52037dea464fd4a8eb060d32c92a9bd0`
- Deployment state: `READY`

复核时：

- `https://medicalchannelai.vercel.app` 返回 HTTP 200；
- `/api/status` 返回 HTTP 200；
- status 中 `ready=true`、`degraded=false`；
- 数据源为 `DATABASE`；
- AI 配置可用。

这说明“现在可访问”不能反证现场失败；需要把中国现场网络可达性视为独立风险。

### qd.je 入口

复核时：

- `https://medicalai.qd.je` 最终跳转到 `https://medicalchannelai.vercel.app/today`；
- 它目前不是 Vercel 项目的正式 Custom Domain；
- 当前 Production alias 列表中没有 `medicalai.qd.je`。

因此两个演示地址不是独立故障域：

```
medicalai.qd.je
  -> redirect
  -> medicalchannelai.vercel.app
```

当 `vercel.app` hostname 在现场网络不可达时，两个地址会一起失效。

### Production 漂移

GitHub main 在复核时为：

`f08509134822128f0737a905226f2d7d1725d877`

但 Production 仍运行：

`6ed4a1fa52037dea464fd4a8eb060d32c92a9bd0`

main 后续提交没有成为 Production。当前最新 READY Preview 也来自 feature branch，而不是 main Production。

因此还存在第二个独立问题：

> GitHub 已推进，不代表正式演示地址已经运行最新被接受版本。

## P0 关闭条件

以下条件必须同时满足：

1. `medicalai.qd.je` 作为 Vercel Project Custom Domain 直接提供站点，不再 HTTP 跳转到 `*.vercel.app`；
2. Vercel 显示该域名 Verified，HTTPS 正常；
3. Production 版本与明确接受的 GitHub release commit 对齐；
4. `/`、`/today`、`/api/status` 在公开网络通过；
5. 至少做一次中国现场网络（天津移动/联通/电信或真实手机流量）验证；
6. 保留一个不依赖在线站点的演示兜底（本机/手机预先保存的离线演示）；
7. 演示前 smoke check 成为固定动作。

## 最小修复路线

### A. 先修主域名

在 Vercel Project -> Settings -> Domains 添加：

`medicalai.qd.je`

随后按 Vercel 返回的 verification / CNAME 要求，在该 qd.je 域名当前使用的权威 DNS 服务中配置记录。

DigitalPlat 只负责域名注册/NS delegation；普通 DNS 记录由外部权威 DNS 服务管理。

注意：

- 不删除现有 `medicalchannelai.vercel.app` alias；
- 不把 `medicalai.qd.je` 配成 redirect；
- 目标是浏览器访问后地址栏仍保持 `medicalai.qd.je`。

### B. 修 Production 发布纪律

每次面向外部人员演示前必须记录：

- accepted GitHub commit；
- Production deployment ID；
- `/api/status.commit`；
- 三者必须一致或有明确、已记录的例外。

Preview READY 不等于 Production READY。

### C. 演示前检查

仓库增加 `.github/workflows/public-demo-smoke.yml`。

检查：

- `medicalchannelai.vercel.app`；
- `medicalai.qd.je`；
- `medicalchannelai.vercel.app/api/status`；
- HTTP 成功；
- status.ready=true；
- 输出 qd.je 的最终跳转地址，用于持续发现仍依赖 `vercel.app` 的情况。

## 当前人工阻塞

Vercel MCP 当前可以读取部署，但没有“向项目添加 Custom Domain”的写入动作。

尝试通过 Vercel Dashboard 自动添加域名时，Dashboard 要求交互式登录，自动浏览器没有已保存的 Vercel 登录态，因此未执行任何域名修改。

需要用户完成一次 Vercel 登录/域名添加，或提供一个已授权的 Vercel 浏览器会话；之后才能读取 Vercel 返回的精确 DNS verification 记录并继续完成 qd.je 直连。

## 不做的事

- 不因为当前再次返回 200 就关闭事故；
- 不把另一个 `*.vercel.app` Preview 当“独立备用站”；
- 不在 P0 未关闭前继续为演示可靠性增加无关业务功能；
- 不把美国/海外探针成功等价为天津现场可达。
