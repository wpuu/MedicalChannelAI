# MedicalChannelAI 当前状态

日期：2026-08-30  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`TODAY_ACTIONS_TRUSTED_BACKEND + H5 + SERVER_FOLLOWUP + GROUNDED_OUTREACH + IN_APP_REMINDER + FOLLOWED_OPPORTUNITIES + DEPLOYMENT_SCAFFOLD + DEMO_TO_PILOT_MODE_GUARD`  
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

## 产品闭环

当前已经具备：

- Today Top5；
- trusted Session + 一次性 invite；
- 服务端 tenant-private follow-up；
- 到期站内提醒；
- `/followed` 长期跟进项目；
- grounded on-demand outreach；
- VERIFIED public facts 与客户私有资源分离；
- Agnes 输出必须经过 grounding / allowlist 校验；
- 浏览器不能自报 tenant/profile 作为可信身份。

当前仍无微信、短信、邮件、系统 Push。

## Collector / Discovery

Collector 已支持：

`官方详情 → VERIFIED event/facts → event ledger → lifecycle rebuild → current projection → taxonomy → institution enrichment → today_repo`

自动 listing discovery 仍严格只有 **2/7**：

1. `tjmugh_procurement`
2. `tj_first_central_hospital_procurement`

其余5个 Source 继续 fail-closed，不猜 classId/pagination，不绕 CAPTCHA。

## 给老杨看的地址：同域两阶段

当前推荐：

1. `medradar.qzz.io`
2. `medicalai.qzz.io`
3. `medradar.dpdns.org`
4. `mcai.dpdns.org`

DigitalPlat Domains 当前官方仍列出 `*.qzz.io` 和 `*.dpdns.org` 为 Available public namespaces，并允许连接外部 DNS provider。实际具体名称是否可注册仍以申请平台实时结果为准。

### 第一步：Demo

同一域名先发布明确标注“演示数据”的 Mock H5：

```text
VITE_BUILD_MODE=demo
VITE_API_BASE_URL=
```

- 虚构天津医疗项目；
- 不登录；
- 不调用真实 Agnes；
- 不冒充真实医院采购数据。

### 第二步：真实 Pilot

验证完成后仍用同一个网址重新构建：

```text
VITE_BUILD_MODE=pilot
VITE_API_BASE_URL=/api
```

然后启用真实 invite/Session、客户画像、采购事实、follow-up、reminder、followed、outreach。

前端已经增加 build-mode fail-closed，防止 Demo/Pilot 串模式。

## 部署脚手架

结构：

`域名 → Cloudflare（可选/推荐）→ Caddy → 单台 VPS → H5 + /api → 127.0.0.1:8787 + /srv/medical/data/pilot.sqlite`

仓库已有：

- `deploy/README.md`
- `deploy/README_DOMAIN.md`
- `deploy/Caddyfile.example`
- `deploy/caddy-medical.env.example`
- `deploy/build-web.sh`
- `deploy/pilot-smoke.sh`
- API/discovery/backup/healthcheck systemd service/timer
- `pilot_backup.py`
- `GET /api/healthz`

### Health

`GET /api/healthz` 只返回固定非敏感 liveness，不包含 tenant/profile、业务数据、Provider/model/API Key。

### Backup

SQLite 使用 `Connection.backup()` 在线备份，之后执行 `PRAGMA integrity_check` 并计算 SHA-256；默认北京时间每天02:20，保留14份。真实 Pilot 前仍需 backup + restore 实测。

### HTTPS

Cloudflare 最终使用 `Full (strict)`。首次源站证书建议先 DNS-only 直连 Caddy，确认 HTTPS 后再开启代理。

这些只是**部署脚手架已写入**，尚未在真实 VPS 执行，不能称为已经上线。

## CI / Build 真相

CI 现在定义了：

- Python compile + 81组 unittest；
- JSON 校验；
- deploy shell syntax；
- TypeScript typecheck；
- **Demo H5 build**；
- **Pilot H5 build**。

最新实际检查：HEAD `ea1cabf5ee3cacc47dfa4b98d27ee4c937e14a3b`，Run `33304701302`：

- web-build `99239055207`：`runner_id=0 / steps=[] / failure`
- python-pilot `99239055274`：`runner_id=0 / steps=[] / failure`

所以所有这些步骤仍然**一个都没有真正执行**。81个 test modules 只是“已写入”，不能标 PASS。

## 下一步

1. 如果 `medradar.qzz.io` 可注册，优先固定它作为给老杨看的同域 Demo/Pilot 地址；不可用则依次退到其他候选；
2. 获得81组 tests + Demo/Pilot 两种 H5 build 的真实 PASS；
3. 可以先部署明确标注演示数据的 Demo 给老杨看；
4. deterministic PASS 后做 server-only Agnes grounded outreach smoke；
5. 在同一域名切真实 Pilot，做 HTTPS + Session/invite/follow-up/reminder/followed/outreach smoke；
6. backup + restore 实测；
7. 真实 discovery tick latency；
8. 逐个解决剩余5个 discovery contract；
9. 捕获 `downEnId` 医疗附件真实 bytes；
10. 运行28个 Agnes benchmark。
