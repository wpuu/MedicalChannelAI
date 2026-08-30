# Demo / Pilot 域名建议

## 当前决定

给老杨看的**静态商务 Demo** 当前固定优先：

```text
https://medicalai.qd.je/
```

原因不是它在 DNS 技术上最“标准”，而是已经完成了最重要的目标环境实测：

- 中国大陆普通网络可以打开；
- 微信内置浏览器可以直接点击打开。

相反，`medradar.dpdns.org` 在当前微信实测中打不开，因此不再作为商务 Demo 首选。即使原因可能是微信信誉/黑名单且未来会变化，产品决策仍按当前真实用户体验执行。

## qd.je 的边界

`qd.je` 当前存在 Public Suffix List / Cloudflare zone 兼容问题：不同 `*.qd.je` 在部分基础设施中不能像独立注册域那样处理。

因此当前明确：

```text
medicalai.qd.je = 静态商务 Demo
```

它不承诺成为长期正式品牌域名，也不默认承载未来带真实客户 Session/画像/跟进数据的正式 Pilot。

正式 Pilot / 收费版优先换独立长期可控域名。

## 为什么 Demo 可以使用 qd.je

当前 Demo：

- 无登录；
- 无 Session Cookie；
- 无真实客户画像；
- 无真实采购数据；
- 无真实 Agnes Key；
- 全部为明确标注的虚构演示数据。

所以 qd.je 的 PSL 隔离问题不会给当前静态 Demo 引入客户数据风险。

## 为什么不再优先 dpdns.org

`dpdns.org` 在标准 DNS / PSL / Cloudflare 接入上更成熟，但商务演示的第一目标是：

> 老杨能否在微信里直接点开。

当前真实测试已经显示 `medicalai.qd.je` 能打开，而 `medradar.dpdns.org` 不能打开。

所以商务 Demo 选择 qd.je；dpdns.org 只保留为技术备用/对照，不用于当前微信演示入口。

## 免费域名的信誉风险

免费公共后缀的微信/浏览器/安全厂商信誉可能变化。当前也有社区报告 DigitalPlat 多个公共后缀曾出现在第三方域名信誉/黑名单系统中。

因此：

- 不把免费域名写进长期合同/品牌物料；
- 发给老杨前当天再次用微信测试；
- 如果 `medicalai.qd.je` 后续被微信拦截，只换 Demo 域名，不迁产品数据；
- 正式商业版购买独立域名。

## DNS / 托管

Demo 不要求 Cloudflare。

`qd.je` 当前不能稳定作为普通 Cloudflare zone 接入，因此优先使用 DigitalPlat 委派的 DNS provider / deSEC 等能管理该子域 DNS 的方案，直接解析到源站。

当前 Demo 推荐：

```text
medicalai.qd.je
  ↓ DNS
香港 / 日本 / 新加坡优先的境外源站
  ↓ HTTPS
Caddy
  ↓
静态 H5
```

如果现有美国 VPS 在中国大陆和微信实测足够快，可以先零新增成本使用；如果慢，再只换源站 IP。

## 正式版

真实 Pilot 开始写入真实客户画像、follow-up、提醒、Session 前，优先购买独立域名，例如最终品牌对应的 `.com/.cn` 等，并继续保持 H5 + `/api` 同源。

数据库和产品代码不依赖免费域名，因此换域名不需要重建业务数据。
