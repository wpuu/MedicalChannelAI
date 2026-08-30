# MedicalChannelAI 当前状态

日期：2026-08-30  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`TRUSTED_TIANJIN_BACKEND + BUSINESS_DEMO_POLISHED + WECHAT_MAINLAND_ACCESS_GATE + SINGLE_HOST_DEPLOYMENT_SCAFFOLD`  
生产就绪：**false**  
Draft PR：**#1（保持 Draft，不合并）**

## 当前真实规模

- 7 个运行时 P0 Source：4 `IMPLEMENTED`、3 `PARTIAL_IMPLEMENTATION`
- 50 条 VERIFIED 天津商机 fixture
- 15 条 Institution Evidence
- 41 份 Schema/合同
- 81 组 deterministic unittest 模块已写入，尚无真实执行 PASS
- 真实医疗附件 bytes=0
- Agnes benchmark 28 case，未执行
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`

## 当前近期目标

### A. 先上线给老杨看的商务 Demo

Demo 已完成商务收口：

- TOP1 = 智能采血与标本前处理；
- 虚构演示客户画像；
- 明确解释 TOP5 = 公开项目字段 × 当前客户医院关系/产品能力；
- 所有医院、项目、联系人、金额均为虚构；
- 卡片/详情使用“演示公开字段 / 演示客户资源”；
- Demo 官方依据不跳真实政府页面暗示虚构公告存在；
- 依据不足时禁止生成沟通话术；
- 支持一键重置演示；
- Mock 不携带内部 `model_requests`；
- 不出现永远转圈的假 AI 队列；
- robots meta + robots.txt + X-Robots-Tag 禁止搜索引擎收录；
- `docs/product/demo.md` 固定5分钟商务演示路径。

### B. 后端并行验证真实天津 Pilot

真实 Pilot 代码已具备 Today Top5、Session/invite、服务端 follow-up、站内 reminder、`/followed`、grounded outreach 和 tenant 隔离；但81组后端 tests 仍没有真实 PASS，因此不能上线真实客户数据。

## Demo 地址已经按真实微信测试调整

当前静态商务 Demo 地址优先：

```text
https://medicalai.qd.je/
```

用户已实测：

- 中国大陆网络可以访问；
- 微信内置浏览器可以直接点击打开。

当前 `medradar.dpdns.org` 微信实测打不开，因此不作为商务 Demo 入口。

这里以真实目标环境优先，不以理论 DNS/Cloudflare 兼容性反向覆盖实际体验。

## qd.je 只用于静态 Demo

`qd.je` 当前仍存在 Public Suffix List / Cloudflare zone 兼容问题。

所以当前明确：

- `medicalai.qd.je`：无登录、无真实客户数据的商务 Demo；
- 真实 Pilot / 收费版：优先换独立长期可控域名。

不再强求免费 Demo 域名与真实 Pilot 永久同域。

## 微信 / 大陆访问已经变成硬门槛

发给老杨前必须：

1. 微信内置浏览器直接点击可打开；
2. 至少2条独立中国大陆网络可访问；
3. 全程关闭 VPN/Clash/WARP；
4. HTTPS无警告；
5. 首页、TOP1详情、刷新、返回、Demo话术、重置均正常。

完整验收：`deploy/CHINA_ACCESS.md`。

由于免费公共后缀信誉可能变化，每次重要演示当天必须重新在微信点击验证。

## Demo 网络拓扑

```text
medicalai.qd.je
  ↓ DNS
境外源站（香港 > 日本 > 新加坡 > 美国测试）
  ↓ HTTPS/Caddy
静态 H5
```

Demo 不依赖 Cloudflare/Vercel。

如果现有美国 VPS 在微信/天津网络足够快，可以零新增成本先用；如果慢，只换亚洲源站和 DNS IP，不改产品。

## H5 国内访问优化

Demo 首屏禁止依赖 Google Fonts、jsDelivr、unpkg、cdnjs、Google APIs、Vercel/Pages/Workers 默认域等第三方运行资源。

`deploy/build-web.sh demo` 当前执行：

- `npm ci`
- `npx tsc --noEmit`
- `npm run build`
- HTML/CSS 外部运行依赖扫描
- 默认3 MiB dist大小预算

Caddy 对 `/assets/*` 使用 immutable 长缓存，SPA HTML使用 `no-cache`。

## Collector / Discovery

Collector 已支持：

`官方详情 → VERIFIED event/facts → event ledger → lifecycle rebuild → current projection → taxonomy → institution enrichment → today_repo`

自动 listing discovery 仍只有 2/7：

1. `tjmugh_procurement`
2. `tj_first_central_hospital_procurement`

其余5个继续 fail-closed，不猜 classId/pagination，不绕 CAPTCHA。

## CI 真相

GitHub Actions 仍存在 runner 未分配问题：job `runner_id=0 / steps=[]`，没有真实运行 TypeScript/build/Python tests。

因此：

- GitHub Actions 不再阻塞静态 Demo；
- Demo 在实际目标服务器构建并通过微信/大陆验收即可获得真实前端证据；
- 81个 Python tests 仍不能标 PASS；
- 真实 Pilot 不得提前上线。

## 下一步

1. 继续使用已经可访问的 `medicalai.qd.je` 作为商务 Demo 地址；
2. 将该域名 DNS 指向选定 Demo 源站；
3. 目标服务器运行 `deploy/build-web.sh demo`；
4. Caddy HTTPS；
5. 严格执行 `deploy/CHINA_ACCESS.md` 微信 + 两条大陆网络验收；
6. 按 `docs/product/demo.md` 完整走查；
7. 通过后再把链接发给老杨；
8. 并行获得81组后端 tests PASS、Agnes smoke，并为真实 Pilot 准备独立域名。
