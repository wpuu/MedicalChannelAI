# MedicalChannelAI 当前状态

日期：2026-08-30  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`TRUSTED_TIANJIN_BACKEND + BUSINESS_DEMO_POLISHED + SINGLE_HOST_DEPLOYMENT_SCAFFOLD`  
生产就绪：**false**  
Draft PR：**#1（保持 Draft，不合并）**

## 当前真实规模

- 7 个运行时 P0 Source：4 `IMPLEMENTED`、3 `PARTIAL_IMPLEMENTATION`
- 50 条 VERIFIED 天津商机 regression fixture
- 15 条 Institution Evidence
- **41 份 Schema/合同**
- **81 组 deterministic unittest 模块已写入，尚未获得真实执行 PASS 证据**
- 真实医疗附件 bytes=0
- Agnes benchmark 28 case，未执行
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`

## 当前近期目标已经调整

不再等真实天津后端全部验证完才让客户看页面。

现在分成两条线：

### A. 先上线商务 Demo

目标：先让老杨验证“每天给我5个值得跟的项目”这个产品价值。

Demo 已经专门做过商务演示收口：

- TOP1 改为“智能采血与标本前处理系统”，更贴合天津渠道客户资源；
- 顶部明确展示“虚构演示客户画像”；
- 排名明确解释为“项目公开事实 × 当前客户医院关系/产品能力”，不是普通招标搜索排行；
- 所有医院、项目、联系人、金额都明确为虚构；
- Demo 卡片使用“演示公开字段 / 演示客户资源”，不冒充真实官方事实或真实客户画像；
- 官方依据在 Demo 中只展示入口形态，不跳转去暗示虚构项目有真实公告；
- 公开依据不足时，首页、详情和 Mock Service 三层都禁止生成沟通话术；
- `VERIFIED/PARTIAL/UNVERIFIED` 等技术枚举已经改成“已核实/部分核实/未核实”；
- 支持“一键重置演示”，演示前可清掉浏览器上次操作的跟进状态；
- Mock 响应不再嵌入内部 `model_requests` 数据；
- `robots meta + robots.txt + X-Robots-Tag` 全部禁止搜索引擎收录虚构采购内容；
- 5分钟演示流程已经写入 `docs/product/demo.md`。

Demo 构建：

```text
VITE_BUILD_MODE=demo
VITE_API_BASE_URL=
```

不登录、不调用真实 Agnes、不依赖真实天津数据。

### B. 后续同域切真实 Pilot

真实后端通过验证后，同一个网址重新构建：

```text
VITE_BUILD_MODE=pilot
VITE_API_BASE_URL=/api
```

然后才启用真实 invite/Session、客户画像、采购事实、follow-up、reminder、followed、outreach。

前端已经有 build-mode fail-closed，避免 Demo/Pilot 串模式。

## 给老杨看的地址

当前推荐：

1. `medradar.qzz.io`
2. `medicalai.qzz.io`
3. `medradar.dpdns.org`
4. `mcai.dpdns.org`

DigitalPlat Domains 当前官方仍列出 `*.qzz.io` 和 `*.dpdns.org` 为 Available public namespaces，并支持外部 DNS provider。具体 `medradar` 是否可注册仍以申请平台实时结果为准。

正式收费版仍建议换独立长期可控域名。

## 产品闭环

真实 Pilot 代码当前已经具备：

- Today Top5 + 详情；
- opaque Session + 一次性 invite；
- tenant-private append-only follow-up；
- 到期站内提醒；
- `/followed` 长期跟进；
- grounded on-demand outreach；
- VERIFIED public facts 与客户私有资源分离；
- Agnes 输出 grounding / allowlist 校验；
- 浏览器不能自报 tenant/profile 作为可信身份。

当前仍无微信、短信、邮件、系统 Push。

## Collector / Discovery

Collector 已支持：

`官方详情 → VERIFIED event/facts → event ledger → lifecycle rebuild → current projection → taxonomy → institution enrichment → today_repo`

自动 listing discovery 仍严格只有 **2/7**：

1. `tjmugh_procurement`
2. `tj_first_central_hospital_procurement`

其余5个 Source 继续 fail-closed，不猜 classId/pagination，不绕 CAPTCHA。

## 单机部署脚手架

结构：

`域名 → Cloudflare（可选/推荐）→ Caddy → 单台 VPS → H5 + /api → 127.0.0.1:8787 + /srv/medical/data/pilot.sqlite`

仓库已有：

- `deploy/README.md`
- `deploy/README_DOMAIN.md`
- `deploy/Caddyfile.example`
- `deploy/caddy-medical.env.example`
- `deploy/build-web.sh demo|pilot`
- `deploy/pilot-smoke.sh`
- API/discovery/backup/healthcheck systemd service/timer
- `pilot_backup.py`
- `GET /api/healthz`

`build-web.sh` 已移除 `rsync` 额外依赖，只使用标准 shell/coreutils + npm。

Demo 可以直接在目标 VPS 上运行：

```text
bash deploy/build-web.sh demo
```

它会真实执行 `npm ci + npx tsc --noEmit + npm run build`。因此即使 GitHub Actions 继续不可用，也可以在目标 VPS 获得真实 H5 构建证据。

真实 Pilot 仍必须额外通过81组后端测试和 authenticated smoke。

## CI / Build 真相

最新检查 HEAD：`298b07380febc5f48125109851ad7076b0d97385`  
Run：`33306414450`

- web-build `99243650826`：runner 未分配，steps=null
- python-pilot `99243650961`：runner 未分配，steps=null
- job log blob 不存在

因此 GitHub Actions 仍没有真正执行任何代码。现在不再让这个无效 runner 阻塞静态 Demo；目标 VPS 可以作为 H5 的可信构建环境。

81个 Python test modules 仍只是“已写入”，**不能标 PASS**，所以真实 Pilot 仍不能上线。

## 下一步

1. 注册 `medradar.qzz.io`；不可用则退到 `medradar.dpdns.org` 等候选；
2. 在一台 VPS 上运行 `deploy/build-web.sh demo`，拿到真实 `npm ci + TypeScript + build` PASS；
3. 用 Caddy HTTPS 发布明确标注虚构数据的 Demo；
4. 按 `docs/product/demo.md` 做一次浏览器演示走查，然后给老杨看；
5. 根据老杨是否愿意导入自己的医院关系/产品数据决定下一轮产品重点；
6. 与 Demo 验证并行，后端继续等待/寻找可信执行环境完成81组 deterministic tests；
7. 后端 PASS 后再做 server-only Agnes smoke，并在同一域名切真实天津 Pilot；
8. 之后继续剩余5个 discovery contract、附件真实 bytes 和28个 Agnes benchmark。
