# MCAI-DEMO-AVAIL-001 · 演示站可用性 P0

DATE=2026-09-27T21:22:00+08:00  
UPDATED=2026-09-28T09:22:00+08:00  
MODEL=GPT-5.6 Sol High  
SEVERITY=P0  
STATUS=OPEN

## 用户要求

`medicalai.qd.je` 必须继续可访问。

同时，原 `35.211.124.40` GCP VPS 已产生接近 3 美元费用，不能继续作为 MedicalChannelAI 的长期入口。

因此目标不是退役 qd.je，而是：

> 保留 medicalai.qd.je，移除常驻付费 VPS 依赖。

## 当前事实

### Vercel 主站

当前应用主站：

- https://medicalchannelai.vercel.app
- Production 已运行已接受版本；
- `/api/status` 为 `ready=true`；
- 数据源 `DATABASE`；
- 快照 `FRESH`；
- AI 可用。

### qd.je

当前：

- `medicalai.qd.je` 仍解析到 `35.211.124.40`；
- 该 A 记录暂时不能删除，否则 qd.je 会立即失去现有入口；
- Vercel 对 qd.je 的直接 Custom Domain 验证存在 PSL/父域验证冲突；
- 新入口完成前禁止释放旧 VPS。

## 当前主方案

主方案已从 Firebase Hosting 调整为托管 HTTPS redirect edge。

权威任务：

`docs/ops/MCAI-QDJE-ZEROCOST-004-2026-09-28.md`

主路线：

```text
medicalai.qd.je
  -> redirect.pizza（免费托管 HTTPS Redirect）
  -> medicalchannelai.vercel.app/today
```

原因：

- 不需要常驻 VM；
- 免费计划足够当前流量；
- 自动 HTTPS；
- 固定进入 `/today`，Query forwarding 开启；
- 配置比新增 Firebase 项目更少。

Firebase Hosting 配置继续保留为 fallback，不再作为第一选择。

## P0 关闭条件

1. `medicalchannelai.vercel.app` 正常；
2. `medicalai.qd.je` 正常；
3. qd.je 不再解析到 `35.211.124.40`；
4. qd.je HTTPS 正常；
5. Path forwarding 关闭、Query forwarding 开启，行为符合预期；
6. GCP 中不再保留仅为本入口计费的 VM / 静态 IPv4；
7. 天津真实手机网络至少验证一次；
8. public demo smoke 持续检查两个入口。

## 不做的事

- 不退役 medicalai.qd.je；
- 不再为 qd.je 保留常驻付费 VPS；
- 不在新入口准备好前删除当前 A 记录；
- 不继续死磕 Vercel 的 qd.je Verification Required。
