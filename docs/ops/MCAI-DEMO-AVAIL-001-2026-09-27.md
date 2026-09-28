# MCAI-DEMO-AVAIL-001 · 演示站可用性 P0

DATE=2026-09-27T21:22:00+08:00  
UPDATED=2026-09-28T10:36:00+08:00  
MODEL=GPT-5.6 Sol High  
SEVERITY=P0  
STATUS=OPEN

## 当前要求

`medicalai.qd.je` 必须在中国大陆可正常使用。

仅仅 302 到 `medicalchannelai.vercel.app` 不算通过，因为浏览器最终仍直接访问 Vercel。

## 已解决

- Vercel Production 正常；
- status ready=true；
- DATABASE/FRESH；
- AI 可用；
- qd.je 已脱离原付费 GCP IP；
- redirect.pizza 临时入口可在海外环境跳到 Vercel。

## 当前主线

权威任务：

`MCAI-CN-ENTRY-006`

文档：

`docs/ops/MCAI-CN-ENTRY-006-2026-09-28.md`

架构：

```text
国内浏览器
 -> medicalai.qd.je
 -> Tencent EdgeOne Pages Edge Function
 -> medicalchannelai.vercel.app
```

浏览器不得看到或跳到 Vercel hostname。

## 已排除

### redirect.pizza

只能 30x，无法解决国内浏览器直接访问 Vercel。

### Alibaba ESA Entrance

免费 Entrance 套餐不支持把 subdomain 作为独立 website；我们只控制 `medicalai.qd.je`，不控制 `qd.je`，因此不作为免费主线。

## P0 关闭条件

1. `medicalai.qd.je` 地址栏保持；
2. `/today` 正常；
3. `/api/status` 正常；
4. AI 请求正常；
5. 不发生浏览器跳转到 Vercel；
6. 天津真实手机网络通过；
7. 不依赖常驻付费 VPS；
8. smoke 检查代理入口本身。
