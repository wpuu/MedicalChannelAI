# MCAI-DEMO-AVAIL-001 · 演示站可用性 P0

DATE=2026-09-27T21:22:00+08:00  
UPDATED=2026-09-28T10:30:00+08:00  
MODEL=GPT-5.6 Sol High  
SEVERITY=P0  
STATUS=OPEN

## 当前用户要求

`medicalai.qd.je` 必须在中国大陆可正常使用。

“能跳转到 Vercel”不算通过，因为 `*.vercel.app` 本身在中国大陆网络不可作为可靠正式入口。

## 已解决

- Vercel Production 正常；
- `/api/status ready=true`；
- DATABASE/FRESH；
- AI 可用；
- 已移除 `35.211.124.40` 作为 DNS 正式目标；
- qd.je 当前临时切到 redirect.pizza。

## 尚未解决

当前 redirect.pizza 只是 302：

```text
medicalai.qd.je
 -> redirect.pizza
 -> medicalchannelai.vercel.app
```

因此中国大陆浏览器仍直接访问 Vercel。

该路线不能关闭本 P0。

## 当前权威方案

任务：

`MCAI-CN-ENTRY-005`

文档：

`docs/ops/MCAI-CN-ENTRY-005-2026-09-28.md`

方案：

```text
国内用户
 -> medicalai.qd.je
 -> Alibaba Cloud ESA reverse proxy
 -> medicalchannelai.vercel.app origin
```

要求浏览器地址栏保持 qd.je，不发生 Vercel hostname 跳转。

第一阶段使用 ESA Entrance 免费套餐 + Global (Excluding Chinese Mainland) + CNAME 接入，源站仍为 Vercel。

## P0 关闭条件

1. `medicalai.qd.je` 地址栏保持不变；
2. `/today` 正常；
3. `/api/status` 正常；
4. AI 动态请求正常；
5. 不出现到 `*.vercel.app` 的浏览器 30x；
6. 天津真实手机网络验证通过；
7. 不依赖常驻付费 VPS；
8. public demo smoke 能检测 qd.je 代理入口本身，而不是只跟随重定向判断成功。

## 不做的事

- 不把 redirect.pizza 的 302 当作中国大陆可用性解决；
- 不重新启用付费 GCP VPS；
- 不声称未备案域名已经获得中国大陆 CDN 节点；
- 不在 ESA 给出精确 CNAME 前猜 DNS 值。
