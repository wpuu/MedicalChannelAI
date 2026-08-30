# MedicalChannelAI 当前状态

日期：2026-08-30  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`M1_FACT_PIPELINE + M2_MATCHING_SUBSCRIPTION + TODAY_ACTIONS_TRUSTED_BACKEND + H5_AUTH_SINGLE_HOST_RUNTIME + PERSISTENT_DISCOVERY + SERVER_FOLLOWUP + GROUNDED_OUTREACH + IN_APP_REMINDER + FOLLOWED_OPPORTUNITIES_INITIAL`  
生产就绪：**false**  
Draft PR：**#1（保持 Draft，不合并）**

## 当前真实规模

- 7 个运行时 P0 Source：4 `IMPLEMENTED`、3 `PARTIAL_IMPLEMENTATION`
- 50 条 VERIFIED 天津商机 regression fixture
- 15 条 Institution Evidence
- **40 份 Schema/合同**
- **79 组 deterministic unittest 模块已写入，尚未获得真实执行 PASS 证据**
- 真实官方附件 bytes=0；医疗附件 bytes=0
- Agnes benchmark 28 case，未执行
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`

## Today Actions / Auth / H5

当前可信链路：

`Public collector → event ledger → current opportunity projection → Match/Score → Today Actions → input SHA-256 → Agnes queue/global lease → grounded validation → Public View`

已具备：

- 最终 Today Action 最多5张；
- 官方事实 / Evidence / 客户私有上下文 / Priority / AI Decision 分离；
- 无 VERIFIED grounded facts 时阻止模型建议；
- 越权或无依据模型输出拒绝；
- opaque Session + SHA-256 server-side storage；
- 一次性 invite；
- `__Host-mcai_session; Secure; HttpOnly; SameSite=Strict`；
- tenant/profile 只能来自 trusted Session；
- same-origin `/api/*`；
- 单机 SQLite Pilot 默认后端监听 `127.0.0.1:8787`；
- H5 API 模式 401 自动回登录；Mock 模式继续可独立演示。

## 服务端 Follow-up

已有：

- `GET /api/followup/:opportunity_id`
- `POST /api/followup/:opportunity_id`
- append-only tenant/profile-private 跟进历史
- profile 级 `mutation_id` 幂等
- NOT_FIT 画像复核建议但 `auto_apply_allowed=false`
- `remind_at` 服务端持久化

公开采购事实绝不因为客户跟进而被修改。

## 站内到期提醒已接通

链路：

`稍后提醒 → timezone-aware remind_at → 服务端保存 → 到期 → GET /api/reminders → Today 首页站内提醒 → POST /api/reminders/:id/ack`

关键边界：

- H5 日期选择会转换为用户本地所选日期 09:00 的完整 ISO datetime；
- 只从每个商机当前最新 follow-up 派生提醒；
- reminder ack 是 tenant/profile-private 且幂等；
- reminder Public View exact-shape fail-closed；
- 当前只承诺“打开 H5 时看到站内提醒”；
- **没有微信、短信、邮件或系统 Push**，不能宣称后台主动通知已经完成。

## 我的跟进 `/followed`

新增长期跟进视图，解决商机掉出 Today Top5 后无法继续查看的问题。

后端：

- `followed_store.py`
- `followed_http.py`
- `GET /api/followed`
- `medical-followed-opportunities-public.schema.json`

H5：

- `/followed`
- `FollowedPage.tsx`
- `followedApi.ts`
- 顶部导航“我的跟进”

规则：

- Today Top5 = 今天最值得行动的商机；
- 我的跟进 = 已进入销售流程、需要长期维护的商机；
- 不把历史跟进项目强行塞回 Today Top5；
- 每个项目只取当前最新 follow-up 状态，默认排除 `ARCHIVED`；
- 再关联同一份共享 public opportunity + VERIFIED official evidence；
- Public View 不返回 tenant/profile/followup_id；
- 到期提醒仍在 Top5 时进入今日详情；掉出 Top5 时进入 `/followed?focus=...`；
- 已修复字符串金额预算（例如 `5730000.00`）在 followed 视图被误当空值的问题。

## Grounded on-demand Outreach

真实 H5 已接 `POST /api/outreach/:opportunity_id`。

链路：

`trusted Session → tenant-private profile + VERIFIED public facts → locked input → SHA cache → shared Agnes global lease → allowlisted code/reference → validation → server-rendered Chinese draft → H5`

边界：

- 浏览器不能提交自由 prompt、tone、tenant/profile；
- 至少需要 VERIFIED `buyer_name + project_name`；
- Agnes 不直接编写客户可见采购事实或自由销售文案；
- 未知 fact_id/profile path、缺核心引用、越权 code 全部拒绝；
- 最终话术由服务端模板渲染；
- 固定声明“不是医院官方表述，不代表中标概率或采购承诺”；
- `requires_human_confirmation=true`；
- 同一 locked input 用 SHA-256 cache，重复点击不重复调用模型；
- outreach 和 Today Actions 共用 Agnes global lease；
- Key 只来自服务端 `MCAI_AGNES_API_KEY`，不进 GitHub/SQLite/H5/Public View。

## Collector / Discovery

Collector 已支持：

`抓取 → parse → VERIFIED event/facts → public event ledger → lifecycle rebuild → current projection → taxonomy → institution enrichment → today_repo`

自动 listing discovery 仍严格只有 **2/7**：

1. `tjmugh_procurement`
2. `tj_first_central_hospital_procurement`

其余5个 Source 继续 fail-closed：

- 天津财政 native list route 未解决；
- TJGPC 采购公告 classId/pagination 未解决；
- CCGP 地方公告当前 canonical list 不是天津专属；
- CCGP 采购意向 CAPTCHA/query contract 未固定；
- 天津公共资源结果列表 contract 未固定。

## 部署方案已冻结

见：`docs/project/deployment-plan-v0.1.md`

天津 Pilot 首版：

`Pilot 域名 → Cloudflare（推荐）→ 单台长期在线 VPS → HTTPS reverse proxy → web/dist + /api → 127.0.0.1:8787 + /srv/medical/pilot.sqlite`

关键决定：

- H5 与 API 保持同一 origin；
- `VITE_API_BASE_URL=/api`；
- `dpdns.org` 一类免费域名可以作为 Pilot 临时入口；
- 正式收费商业版改独立长期可控域名；
- Cloudflare 源站 TLS 目标为 `Full (strict)`；
- 当前 SQLite runtime 禁止直接复制成多 VPS/多容器/无共享磁盘 Serverless；
- Vercel Function 本地文件系统不能充当 `pilot.sqlite` 持久数据库。

## CI / Build 真相

unittest discover 已改为 repository top-level package 模式：

```text
python -m unittest discover -s tools/medical_pilot -t . -p "test_*.py" -v
```

但 GitHub Actions runner 仍未实际分配。

最新**代码**验证触发点：HEAD `426a77387a16257e200214f3037e8eaa9da0c062`，Run `33302048917`：

- `web-build` Job `99231908976`：`runner_id=0 / steps=[] / failure`
- `python-pilot` Job `99231908996`：`runner_id=0 / steps=[] / failure`

因此没有执行 compileall、79组 unittest、JSON validation、npm install、TypeScript typecheck 或 H5 build。

79个 test modules 只能说“已写入”，**不能标 PASS**。当前 failure 仍是 runner 未分配，不是 assertion/build failure。

## Agnes / Attachment / TJGPC

Agnes Pilot 继续固定：

- `agnes-2.5-flash`
- <=12 starts / 60s
- start spacing >=5s
- max in-flight=2
- 0–2s stable jitter
- Provider start 前必须取得 global lease

医疗附件：

`TGPC-2025-A-0164` 精确 `method=downEnId` URL 已确认，但 `URL confirmed != bytes confirmed`；真实医疗附件 bytes 仍为0。

TJGPC `W008` 已确认是网上应答帮助，禁止用于 procurement discovery；真正公告/结果 list classId/pagination 仍待可靠验证。

## 下一步

1. Runner 或等价可信执行环境恢复后，真实执行79组 deterministic tests + H5 typecheck/build；
2. 有 deterministic PASS 后，用 server-only Agnes Key 做 grounded outreach smoke；
3. 按 `deployment-plan-v0.1.md` 在单机 HTTPS Pilot 环境做真实 Session/invite/follow-up/reminder/outreach smoke；
4. 在单机服务器运行 discovery tick 并记录 listing/detail latency；
5. 逐个解决剩余5个 Source discovery contract，不猜 classId/pagination、不绕 CAPTCHA；
6. 捕获 `downEnId` 医疗附件真实 bytes；
7. 运行28个 Agnes benchmark，再用 latency/queue 证据调整 cadence；
8. H5 Pilot 验证后再决定微信原生小程序。
