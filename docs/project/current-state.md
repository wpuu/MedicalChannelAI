# MedicalChannelAI 当前状态

日期：2026-08-30  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION + TODAY_ACTIONS_TRUSTED_BACKEND + H5_AUTH_SINGLE_HOST_RUNTIME + PERSISTENT_DISCOVERY + SERVER_FOLLOWUP + GROUNDED_OUTREACH + IN_APP_REMINDER + FOLLOWED_OPPORTUNITIES + DEPLOYMENT_SCAFFOLD_INITIAL`  
生产就绪：**false**  
Draft PR：**#1（保持 Draft，不合并）**

## 当前真实规模

- 7 个运行时 P0 Source：4 `IMPLEMENTED`、3 `PARTIAL_IMPLEMENTATION`
- 50 条 VERIFIED 天津商机 regression fixture
- 15 条 Institution Evidence
- **41 份 Schema/合同**
- **81 组 deterministic unittest 模块已写入，尚未获得真实执行 PASS 证据**
- 真实官方附件 bytes=0；医疗附件 bytes=0
- Agnes benchmark 28 case，未执行
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`

## Today Actions / Auth / H5

可信主链：

`Public collector → event ledger → current opportunity projection → Match/Score → Today Actions → Agnes queue/global lease → grounded validation → Public View`

已具备：Today Top5、官方事实/客户资源/AI判断分离、opaque Session、一次性 invite、same-origin `/api/*`、服务端 follow-up、站内提醒、grounded outreach 和 `/followed` 长期跟进列表。

浏览器不能把 tenant/profile 作为可信身份；API Key、Provider/model 路由不进入 H5/Public View。

## Follow-up / Reminder / 我的跟进

- `GET/POST /api/followup/:opportunity_id`
- `GET /api/reminders`
- `POST /api/reminders/:reminder_id/ack`
- `GET /api/followed`

跟进数据 tenant/profile-private、append-only；NOT_FIT 只产生画像复核建议，不自动改画像。

“稍后提醒”保存 timezone-aware datetime；到期后打开 H5 可看到站内提醒。当前**没有微信、短信、邮件或系统 Push**。

Today Top5 只表示“今天最值得行动”；已经进入销售流程但掉出 Top5 的项目继续保存在“我的跟进”。到期提醒若已掉出 Top5，会转到 `/followed?focus=...`，不再产生404详情入口。

## Grounded on-demand Outreach

`POST /api/outreach/:opportunity_id`

浏览器不能提交自由 prompt/tone/tenant/profile。Agnes 只允许选择受控策略、问题、定位 code 和已允许 fact/profile 引用；最终中文话术由服务器从 VERIFIED 采购事实和客户确认资源渲染，固定声明“不是医院官方表述，不代表中标概率或采购承诺”。

相同 locked input 使用 tenant/profile-private SHA-256 cache；outreach 与 Today Actions 共用 Agnes global lease。Key 只来自服务端 `MCAI_AGNES_API_KEY`。

## Collector / Discovery

Collector 已支持：

`抓取 → VERIFIED event/facts → public event ledger → lifecycle rebuild → current projection → taxonomy → institution enrichment → today_repo`

自动 listing discovery 当前严格只有 **2/7**：

1. `tjmugh_procurement`
2. `tj_first_central_hospital_procurement`

其余5个 Source 继续 fail-closed，不猜 classId/pagination，不绕 CAPTCHA。

## Pilot 部署脚手架已写入

部署设计：

`Pilot 域名 → Cloudflare（可选/推荐）→ Caddy → 单台长期在线 VPS → H5 + /api → 127.0.0.1:8787 + SQLite`

当前推荐给老杨演示的临时地址候选：

- `mcai.dpdns.org`
- `medicalai.dpdns.org`
- `medai.dpdns.org`

实际是否可注册以申请时为准。正式收费版换自己的独立域名；更换域名不需要迁移数据库或重写 H5/API。

仓库已新增：

- `deploy/Caddyfile.example`
- `deploy/caddy-medical.env.example`
- `deploy/caddy-medical.conf`
- `deploy/medical-pilot.service`
- `deploy/medical-discovery.service` + `.timer`
- `deploy/medical-backup.service` + `.timer`
- `deploy/medical-healthcheck.service` + `.timer`
- `deploy/pilot.env.example`
- `deploy/README.md`
- `deploy/README_DOMAIN.md`

### HTTPS

Caddy 负责源站 HTTPS。若使用 Cloudflare，目标模式为 `Full (strict)`。首次签发源站证书时优先先用 DNS-only 直连源站，确认 Caddy HTTPS 正常后再开启 Cloudflare proxy，可减少证书初始化互相等待的问题。

### 健康检查

新增：

- `health_http.py`
- `GET /api/healthz`
- `medical-health-public.schema.json`

该端点只返回固定的存活状态，不返回 tenant/profile、业务数据、Provider、模型名或 Key。systemd 每5分钟可做本地 healthcheck。它不是业务正确性验收替代品。

### SQLite 在线备份

新增 `pilot_backup.py`，使用 SQLite `Connection.backup()`，不是直接复制活跃数据库文件；备份后执行 `PRAGMA integrity_check`，并输出 SHA-256。

默认 systemd timer：北京时间每日02:20，保留最近14份。正式邀请 Pilot 用户前仍需至少手工跑一次 backup + restore 验证。

当前这些部署文件是**已写入、尚未在真实 VPS 执行**，因此不能称为已经上线。

## CI / Build 真相

GitHub Actions runner 仍未分配。最近已经核实的代码 Run `33302048917`：

- web-build：`runner_id=0 / steps=[]`
- python-pilot：`runner_id=0 / steps=[]`

因此 compileall、**81组** unittest、JSON Schema 校验、TypeScript typecheck 和 H5 build 仍没有真实执行 PASS。

当前 failure 只能解释为 runner 未执行，不是 assertion/build failure；同时也绝不能把静态审查当作 PASS。

## Agnes / Attachment / TJGPC

Agnes Pilot 继续固定：`agnes-2.5-flash`，<=12 starts/60s，start spacing >=5s，max in-flight=2，Provider start 前必须取得 global lease。

`TGPC-2025-A-0164` 的精确 `method=downEnId` 医疗附件 URL 已确认，但真实 bytes 仍为0，继续保持 `URL confirmed != bytes confirmed`。

TJGPC `W008` 已确认是网上应答帮助，禁止用于 procurement discovery；真正公告/结果 list classId/pagination 仍未可靠验证。

## 下一步

1. 获得81组 deterministic tests + H5 typecheck/build 的真实 PASS；
2. 用 server-only Agnes Key 做 grounded outreach smoke；
3. 在一台真实 VPS 执行 `deploy/README.md`，完成 HTTPS、Session/invite/follow-up/reminder/outreach smoke；
4. 手工验证 SQLite backup + restore，再开启每日 timer；
5. 在真实 Pilot host 运行 discovery tick 并记录 listing/detail latency；
6. 逐个解决剩余5个 discovery contract；
7. 捕获 `downEnId` 医疗附件真实 bytes；
8. 运行28个 Agnes benchmark；
9. H5 Pilot 验证后再决定微信原生小程序。
