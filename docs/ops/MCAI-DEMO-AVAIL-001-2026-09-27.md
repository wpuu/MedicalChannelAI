# MCAI-DEMO-AVAIL-001 · 演示站可用性 P0

DATE=2026-09-27T21:22:00+08:00  
UPDATED=2026-09-27T23:20:00+08:00  
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
- Vercel 对 qd.je 的直接 Custom Domain 验证存在 PSL/父域验证冲突，不能再把“直接绑定 Vercel”作为唯一解。

## 决策：零成本 Firebase Hosting 入口

为保留 `medicalai.qd.je`，采用 Firebase Hosting 作为极薄静态入口。

理由：

1. Firebase Hosting 支持自定义域名和自动 SSL；
2. 自定义域名可通过 TXT 验证和 A 记录接入；
3. 不要求常驻 VM；
4. Hosting 有免费额度；
5. 本入口只负责把请求跳转到正式 Vercel Production，资源消耗极低。

目标链路：

```text
medicalai.qd.je
  -> Firebase Hosting（免费静态入口）
  -> 保留原 path/query/hash
  -> https://medicalchannelai.vercel.app
```

## 迁移顺序

必须零中断：

1. 保留现有 `35.211.124.40` A 记录；
2. 创建 Firebase Hosting site；
3. 部署 `ops/qd-je-firebase-redirect/`；
4. 在 Firebase 中添加 `medicalai.qd.je`；
5. 按 Firebase 提供的精确 TXT 验证记录配置 DNS；
6. 等 Firebase ownership/SSL 准备完成；
7. 再把 A 记录从 `35.211.124.40` 改成 Firebase 控制台提供的地址；
8. 验证 `https://medicalai.qd.je` 可访问；
9. 确认不再解析到 `35.211.124.40`；
10. 最后才释放 GCP VM / 静态 IPv4。

严禁先关 VPS 再配置 Firebase。

## P0 关闭条件

1. `medicalchannelai.vercel.app` 正常；
2. `medicalai.qd.je` 正常；
3. qd.je 不再解析到 `35.211.124.40`；
4. qd.je HTTPS 正常；
5. Firebase 入口能保留 path/query/hash 后跳转到 Vercel；
6. GCP 中不再保留仅为本入口计费的 VM / 静态 IPv4；
7. 天津真实手机网络至少验证一次；
8. public demo smoke 持续检查两个入口。

## 不做的事

- 不退役 medicalai.qd.je；
- 不再为 qd.je 保留常驻付费 VPS；
- 不删除当前 A 记录直到 Firebase 新入口完成；
- 不继续死磕 Vercel 的 qd.je Verification Required。
