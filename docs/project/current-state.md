# MedicalChannelAI 当前状态

日期：2026-08-30  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`TRUSTED_TIANJIN_BACKEND + BUSINESS_DEMO_POLISHED + MAINLAND_ACCESS_GATE + SINGLE_HOST_DEPLOYMENT_SCAFFOLD`  
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

## 近期目标

现在分成两条线：

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

### B. 后端继续验证真实天津 Pilot

真实 Pilot 代码已具备：

- Today Top5 + 详情；
- opaque Session + 一次性 invite；
- tenant-private append-only follow-up；
- 到期站内提醒；
- `/followed` 长期跟进；
- grounded on-demand outreach；
- VERIFIED public facts / 客户私有资源分离；
- Agnes grounding / allowlist；
- 浏览器不能自报 tenant/profile。

真实 Pilot 仍不能上线，因为81组后端测试没有真实 PASS。

## 免费域名决定

不再考虑当前收费的 `qzz.io` 作为测试入口。

当前顺序：

1. **`medradar.dpdns.org`** — 首选商务 Demo / 后续同域 Pilot
2. `wpu.dpdns.org` — 用户已有且当前可访问，只作为 dpdns 链路参考，不动现有业务
3. `medicalai.qd.je` — 可注册但不是首选；当前存在 PSL / Cloudflare zone 兼容问题

正式收费后再换独立付费品牌域名。

## 中国大陆访问已经变成硬门槛

给老杨发链接前必须确保：

> 天津普通国内网络、关闭 VPN/Clash/WARP 后可以直接打开。

免费 Demo 默认不依赖 Cloudflare 橙云，不依赖 Vercel：

```text
medradar.dpdns.org
  ↓ DNS-only
境外源站（香港 > 日本 > 新加坡 > 美国）
  ↓ HTTPS/Caddy
静态 H5
```

Cloudflare 普通全球网络不是中国大陆节点服务。其 China Network 属于 Enterprise 独立服务并要求 ICP，因此不作为当前免费 Demo 前置条件。

大陆验收标准见：`deploy/CHINA_ACCESS.md`。

至少：

- 一条国内手机流量；
- 另一运营商或家庭宽带；
- 全程关闭 VPN；
- HTTPS无警告；
- 首页、TOP1详情、刷新、返回、Demo话术、重置均正常。

未通过就不把链接发给老杨。

## H5 国内访问优化

Demo 首屏不允许依赖 Google Fonts、jsDelivr、unpkg、cdnjs、Google APIs、Vercel/Cloudflare Pages 默认域等第三方运行资源。

`deploy/build-web.sh demo` 现在会在 build 后扫描产物；发现外部 `script/link/@import` 运行依赖直接失败。

因此国内访问时，页面只需要成功连接 `medradar.dpdns.org` 本身。

## 部署

Demo 构建：

```text
VITE_BUILD_MODE=demo
VITE_API_BASE_URL=
bash deploy/build-web.sh demo
```

脚本实际执行：

- `npm ci`
- `npx tsc --noEmit`
- `npm run build`
- 外部运行依赖扫描
- 发布到 `/srv/medical/web`

真实 Pilot 后续同域切：

```text
VITE_BUILD_MODE=pilot
VITE_API_BASE_URL=/api
```

单机 Pilot：

`域名 → Caddy → H5 + /api → 127.0.0.1:8787 + pilot.sqlite`

## Collector / Discovery

Collector 已支持：

`官方详情 → VERIFIED event/facts → event ledger → lifecycle rebuild → current projection → taxonomy → institution enrichment → today_repo`

自动 listing discovery 仍只有 2/7：

1. `tjmugh_procurement`
2. `tj_first_central_hospital_procurement`

其余5个继续 fail-closed，不猜 classId/pagination，不绕 CAPTCHA。

## CI 真相

GitHub Actions 仍存在 runner 未分配问题：job `runner_id=0 / steps=[]`，没有真实运行任何 TypeScript/build/Python test。

因此：

- GitHub Actions 不再阻塞静态 Demo；
- Demo 在实际目标服务器构建并验收即可得到真实 H5 PASS 证据；
- 81个 Python tests 仍不能标 PASS；
- 真实 Pilot 不得因此提前上线。

## 下一步

1. 注册 `medradar.dpdns.org`；
2. 先选一个大陆可达的源站；零新增成本可先试现有美国 VPS，有问题立即换香港/日本/新加坡；
3. 在目标服务器运行 `deploy/build-web.sh demo`；
4. 配 Caddy HTTPS；
5. 严格执行 `deploy/CHINA_ACCESS.md` 两条国内网络验收；
6. 按 `docs/product/demo.md` 做完整演示走查；
7. 通过后才把链接发给老杨；
8. 并行解决81组后端测试真实执行、Agnes smoke 和真实天津 Pilot 验收。
