# MedicalChannelAI 当前状态

日期：2026-08-30  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`TRUSTED_TIANJIN_BACKEND + BUSINESS_DEMO_POLISHED + WECHAT_MAINLAND_ACCESS_GATE + CANONICAL_ORIGIN_HARDENING + SINGLE_HOST_DEPLOYMENT_SCAFFOLD`  
生产就绪：**false**  
Draft PR：**#1（保持 Draft，不合并）**

## 当前真实规模

- 7 个运行时 P0 Source：4 `IMPLEMENTED`、3 `PARTIAL_IMPLEMENTATION`
- 50 条 VERIFIED 天津商机 fixture
- 15 条 Institution Evidence
- 41 份 Schema/合同
- **82 组 deterministic unittest 模块已写入，尚无真实执行 PASS**
- 真实医疗附件 bytes=0
- Agnes benchmark 28 case，未执行
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`

## 商务 Demo

当前静态商务 Demo 地址：

```text
https://medicalai.qd.je/
```

用户已在目标环境实测：

- 中国大陆普通网络可以访问；
- 微信内置浏览器可以直接点击打开。

当前 `medradar.dpdns.org` 微信实测打不开，因此不再作为商务入口。这里按真实用户体验决策，不确认其具体失败原因是微信黑名单还是其他信誉/网络策略。

Demo 已完成商务收口：TOP1 智能采血、虚构客户画像、来源分层、依据不足禁止话术、一键重置、无假 AI 排队、禁止搜索引擎收录、5分钟演示流程。

## qd.je 只承担无登录静态 Demo

`qd.je` 当前存在 Public Suffix / Cloudflare zone 兼容限制，因此：

- `medicalai.qd.je`：仅无登录、无真实客户数据的虚构商务 Demo；
- 真实 Pilot：使用独立长期可控 HTTPS 域名；
- 不再要求免费 Demo 域名与真实 Pilot 永久同域。

## 微信 / 中国大陆访问是硬门槛

发给老杨前必须满足 `deploy/CHINA_ACCESS.md`：

1. 微信内置浏览器直接点击可打开；
2. 至少2条独立大陆网络可访问；
3. 全程关闭 VPN/Clash/WARP；
4. HTTPS无警告；
5. 首页、TOP1、刷新、返回、Demo话术、重置正常；
6. 演示当天再次用微信点击验证免费域名没有新拦截。

Demo 推荐拓扑：

```text
medicalai.qd.je
  ↓ DNS
境外源站（香港 > 日本 > 新加坡 > 美国零成本测试）
  ↓ HTTPS / Caddy
静态 H5
```

Demo 不依赖 Cloudflare/Vercel。

## H5 大陆访问优化

`deploy/build-web.sh demo` 当前会执行：

- `npm ci`
- `npx tsc --noEmit`
- `npm run build`
- HTML/CSS 外部运行依赖扫描
- 默认3 MiB dist大小预算

首屏禁止依赖 Google Fonts、jsDelivr、unpkg、cdnjs、Google APIs、Vercel/Pages/Workers 默认域等第三方运行资源。

Caddy 对 Vite hash assets 使用 immutable 长缓存，SPA HTML使用 `no-cache`。

## 真实 Pilot 新增 canonical Host / Origin 防线

真实 Pilot 不再只依赖 `SameSite` Cookie 与反向代理域名配置。

新增：

```text
MCAI_CANONICAL_ORIGIN=https://<independent-pilot-domain>
```

`pilot_server.py` 启动真实后端时必须配置该值，否则 fail-closed 拒绝启动。

API 策略：

- canonical origin 必须是 HTTPS；
- 所有业务 API 请求 `Host` 必须匹配 canonical authority；
- `POST / PUT / PATCH / DELETE` 必须带与 canonical origin 匹配的 `Origin`；
- Host/Origin 不匹配统一返回 `403 {"error":"FORBIDDEN"}`，不泄露具体失败原因；
- 本机 `127.0.0.1 / localhost / ::1` 仅可绕过域名访问 `GET/HEAD /api/healthz`；
- loopback 不能因此访问 `/today` 或写接口。

新增 `test_pilot_origin_policy.py`，覆盖伪造 Host、跨源写请求、sibling origin、本机 health-only 例外和缺失 canonical origin 的启动配置。该模块**已写入但尚未真实执行 PASS**。

## 真实 Pilot 产品链

代码当前已经具备：

- Today Top5 + 详情；
- opaque Session + 一次性 invite；
- tenant-private append-only follow-up；
- 到期站内提醒；
- `/followed` 长期跟进；
- grounded on-demand outreach；
- VERIFIED public facts / 客户私有资源分离；
- Agnes grounding / allowlist；
- 浏览器不能自报 tenant/profile；
- canonical Host/Origin API boundary。

真实客户数据仍不能上线，因为82个测试模块没有真实 PASS。

## Collector / Discovery

Collector 已支持：

`官方详情 → VERIFIED event/facts → event ledger → lifecycle rebuild → current projection → taxonomy → institution enrichment → today_repo`

自动 listing discovery 仍只有 2/7：

1. `tjmugh_procurement`
2. `tj_first_central_hospital_procurement`

其余5个继续 fail-closed，不猜 classId/pagination，不绕 CAPTCHA。

## CI 真相

最新检查 HEAD：`c88b73fa4abfd7e53db66cfd3206063331b1f926`  
Run：`33309593283`

- web-build `99252124011`：未执行任何 step；
- python-pilot `99252124135`：未执行任何 step。

GitHub Actions 仍是 runner 未分配问题。因此：

- 静态 Demo 不再被它阻塞；
- 82个 Python test modules 只是“已写入”，不能标 PASS；
- 真实 Pilot 仍不得提前上线。

## 下一步

1. 保持 `medicalai.qd.je` 作为当前静态商务 Demo 地址；
2. DNS 指向大陆可达源站；
3. 目标服务器运行 `deploy/build-web.sh demo`；
4. Caddy HTTPS；
5. 通过微信 + 两条大陆网络验收；
6. 按 `docs/product/demo.md` 完整走查后再发给老杨；
7. 真实 Pilot 前准备独立 HTTPS 域名并配置 `MCAI_CANONICAL_ORIGIN`；
8. 并行取得82组后端 tests PASS、Agnes smoke、backup restore 和真实 discovery 验证。
