# MCAI-QDJE-ZEROCOST-004 · qd.je 零成本入口切换

DATE=2026-09-28T09:22:00+08:00  
MODEL=GPT-5.6 Sol High  
STATUS=READY_FOR_EXTERNAL_SETUP

## 目标

必须同时满足：

- `medicalai.qd.je` 继续可访问；
- 不再依赖 `35.211.124.40` 常驻 GCP VPS；
- HTTPS 正常；
- 固定进入 `/today`，仅保留查询参数；
- 不引入新的持续服务器账单；
- 切换期间尽量不中断。

## 当前状态

- 正式应用仍由 Vercel 提供：`https://medicalchannelai.vercel.app`；
- `medicalai.qd.je` 当前仍解析到 `35.211.124.40`；
- 在新入口完成前，禁止删除该 A 记录或释放对应 GCP 资源；
- Vercel 直接绑定 qd.je 受 PSL / 父域验证问题阻塞。

## 主方案：redirect.pizza

使用托管 HTTPS Redirect Edge 代替自建 VPS。

目标链路：

```text
medicalai.qd.je
  -> redirect.pizza edge
  -> https://medicalchannelai.vercel.app/today
```

要求：

- 免费计划；
- Source hostname: `medicalai.qd.je`；
- Destination: `https://medicalchannelai.vercel.app/today`；
- Redirect type: 302，切换稳定后可改 301；
- 关闭 path forwarding；
- 开启 query parameter forwarding；
- 自动 HTTPS；
- 不使用 frame redirect。

选择 302 的原因：迁移初期便于回滚，避免浏览器长时间缓存错误的永久跳转。

## 零中断切换顺序

1. 保留当前 `35.211.124.40` A 记录；
2. 在 redirect.pizza 创建 source/destination；
3. 读取 redirect.pizza 为该 hostname 给出的精确 DNS 记录；
4. 若平台支持在 DNS 切换前完成 ownership/certificate 预验证，则先完成；
5. 修改 DigitalPlat DNS；
6. 等权威 DNS 和公共递归 DNS 都不再返回 `35.211.124.40`；
7. 验证 HTTP、HTTPS、固定 `/today` 路径和 query forwarding；
8. 验证天津真实手机网络；
9. 最后释放 GCP VM / 静态 IPv4。

## 回滚

在新入口尚未稳定前：

- 记录原 A：`35.211.124.40`；
- 若新入口失败，可临时恢复原 A；
- 只有新入口连续验证通过后才释放 GCP 资源。

## Firebase 备用

仓库中的 `ops/qd-je-firebase-redirect/` 保留，但降级为备用路线。

只有以下情况才转回 Firebase：

- redirect.pizza 拒绝 `medicalai.qd.je`；
- 无法为该 hostname 签发 HTTPS；
- 要求无法控制的 `qd.je` 父域记录；
- 免费计划条件发生变化。

## P0 关闭条件

- `https://medicalchannelai.vercel.app/today` 正常；
- `https://medicalai.qd.je` 正常跳转；
- qd.je 不再解析到 `35.211.124.40`；
- HTTPS 无证书错误；
- Path forwarding 关闭、Query forwarding 开启，行为符合预期；
- 天津真实手机网络通过；
- GCP 旧入口资源已释放；
- public-demo-smoke 两个入口均通过。
