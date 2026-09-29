# MedicalChannelAI · AI 代理会话交接记录 — 2026-09-29

> 目的：让下一个接手的 AI（或人）不用重新摸索，直接从"当前状态"继续。
> 本文件是**活文档**：每完成一个里程碑就追加一节"进度日志"，并同步更新"当前状态 / 下一步"。
> 工作区根目录还有一份同步副本 `MedicalChannelAI_交接记录_2026-09-29.md`（若两者不一致，以仓库内版本为准）。

---

## 0. 30 秒速览

| 项 | 值 |
|---|---|
| 仓库 | `wpuu/MedicalChannelAI`（私有），默认分支 `main`，`main` 一直**未被改动** |
| 本会话产出的分支 / PR | `docs/strategy-competitive-review-20260929` → **Draft PR #73**（战略评审报告）；`feat/legal-windows-and-tianjin-coverage-20260929` → **Draft PR #74**（§6 工程改动） |
| 报告位置 | `docs/reviews/MCAI-STRATEGY-COMPETITIVE-REVIEW-2026-09-29.md`（只在 PR #73 分支上） |
| 当前正在做 | 报告 §6 工程改动表，按 (1)→(8) 顺序；owner 级决策项跳过（见 §4） |
| 测试基线 | `web/pipeline` Python 套件 **839 通过**（`0701bef`）；`npm run build` 全绿。跑法：`cd web/pipeline && python3 -m unittest discover -s tests`（prebuild 也是这个 cwd） |
| 用户指令 | "按照你的思路做，我相信你，每次过程和结果都保存好，方便下一个 AI 接手" |

---

## 1. 环境恢复（每个新会话先做）

> 2026-09-29 会话 3 实测：沙箱恢复后 `web/node_modules` **和** `.git/config`（remote / 身份 / credential helper）都会丢，先 `cd web && npm ci`，再按下面恢复 git；`web/vite.preview.local.config.ts` 在 `.gitignore` 里（`git status --ignored` 可见），会保留。

沙箱里 `.git/config` **不会跨会话保留**，其余文件会保留。开工前：

```bash
cd /home/user/MedicalChannelAI
git config --get remote.origin.url || git remote add origin https://github.com/wpuu/MedicalChannelAI.git
git config user.name  wpuu
git config user.email wpuu@users.noreply.github.com
git config credential.helper "store --file=/home/user/.git-credentials-mca"
git config core.fileMode false
# PAT 在 /home/user/github_pat.txt（用户提供的临时 PAT，会话结束后用户会销毁）
# GitHub API： PAT=$(cat /home/user/github_pat.txt); curl -H "Authorization: Bearer $PAT" https://api.github.com/user
```

依赖：
- `web/node_modules` 可能不保留 → `cd web && npm ci`
- Python 测试：`cd web && python3 -m unittest discover -s pipeline/tests -t pipeline -p 'test_*.py'`（约 1–2 分钟）
  - 也可直接 `cd web/pipeline && python3 -m unittest discover -s tests -p 'test_*.py'`
- 全量门禁：`cd web && npm run build`（= prebuild gates + Python tests + tsc + vite）
- 快速门禁：`cd web && node scripts/run-prebuild.mjs`

已知沙箱限制：
- `import collector_runtime` 会失败（`ModuleNotFoundError: vercel`）→ runtime 接线只能用"源码文本断言"测试（仓库惯例，参考 `pipeline/tests/test_vercel_regional_runtime.py`）。
- 沙箱无浏览器，前端只能 `tsc` + `vite build` + curl 验证。
- 无法真正发起对 ccgp.gov.cn 的采集（网络 / 反爬），采集效果要等 owner 部署后看 `web/pipeline/data/tianjin_sync_report.json`。

本地预览（可选）：`web/vite.preview.local.config.ts` 是**未跟踪、已加入 `.git/info/exclude`** 的预览配置（allowedHosts + 用打包快照模拟 `/api/public-snapshot`）。启动：
`cd web && VITE_DEMO_DATASET=verified VITE_API_BASE_URL= npx vite --config vite.preview.local.config.ts --host 0.0.0.0 --port 5173`。**不要提交这个文件。**

---

## 2. 已完成（按提交）

### PR #73 · `docs/strategy-competitive-review-20260929`
| 提交 | 内容 |
|---|---|
| `641b6b3` | 战略 / 竞品 / 变现评审报告首版 |
| `e14010a` | 更正：首页 Top5 的表述（客户端默认按天津过滤，不是"老杨看到佳木斯"） |
| `5e4f91a` | 在 §7 前加"进度说明"，指向 PR #74 |

### PR #74 · `feat/legal-windows-and-tianjin-coverage-20260929`（基于 `main@6d49baa`）
| 提交 | 内容 | 对应 §6 项 |
|---|---|---|
| `14cac81` | 法定窗口引擎：`pipeline/medical_channel_pipeline/legal_windows.py`（94 号令 质疑 7 工作日 / 投诉 15 工作日 + 2025–2026 国务院节假日/调休日历）；快照卡片新增顶层 `legal_windows[]`，快照顶层新增 `working_calendar`；JS 镜像 `api/_legalWindows.js`（runtime 刷新仅改 remaining/status，`facts` 不动）；TS 镜像 `src/utils/legalWindows.ts` + `LegalWindowNotice.tsx`；ActionCard / 机会池 / 详情页展示"招标文件质疑期还剩 N 个工作日（推算最晚 M月D日）"；prebuild 新增 `scripts/check-legal-windows.mjs` | (4) 全部，(5) 的倒计时部分 |
| `dcae64f` | 天津深采阶段"未见过的官方 URL 优先"选择（`sync_tianjin_plan.py` 新增 `existing_source_urls_of` / `tianjin_candidate_selection_key` / `select_tianjin_candidates`，`collector_runtime._run_ccgp` 接线）；`tianjin_query_plan.json` 回看 3→7 天、详情 12→16 条、加 2 个 policy 标志；新测试 `pipeline/tests/test_tianjin_candidate_selection.py`（6 个） | (1) 部分 |

关键契约（改动时请保持三端一致：Python / JS / TS）：
- 卡片 `legal_windows: [{code: DOCUMENT_CHALLENGE|RESULT_CHALLENGE, anchor_kind, anchor_date, deadline_date, remaining_working_days, status: OPEN|CLOSED, clock_start_date?, calendar?}] | null`
- 快照 `working_calendar {schema_version "0.1", code "CN_STATE_COUNCIL_2025_2026", coverage_from, coverage_to, holidays[], adjusted_workdays[], legal_basis "MOF_ORDER_94", challenge_working_days 7, challenge_reply_working_days 7, complaint_working_days 15, award_notice_period_working_days 1}`
- 固定算例（Python 测试 + JS 门禁都钉死了）：2026-09-22 起算 7 工作日 → 10-09；09-29 当天剩 4；09-11 → 09-21（9/20 调休上班）；结果公告 09-24 → 公告期满 09-28 → 质疑截止 10-13。
- 天津候选排序键：`(1 if url unseen else 0, published_at, url)` 降序，截到 `max_candidates`。

---

## 3. §6 工程改动表 · 状态板

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| 1 | 采集覆盖：启用中标/更正/终止、放宽天津窗口 | **部分完成** | 未见优先 + 7 天 / 16 条已做。中标/成交类型**未启用**：`load_plan` / `discover_candidates` 对无 VERIFIED 适配器的公告类型是 fail-closed，且 `_actionability` 会把无截止时间的记录判成 PUBLIC_OPPORTUNITY 25 分 → 必须先做 (2) |
| 2 | 中标公告解析 → 品牌/型号/金额 + AWARDED 生命周期 | **完成（A–I）** | 天津 + 京冀辽吉黑 六市场；解析器覆盖 国家模板 / 天津 / 河北 / 黑龙江 / 辽宁(废标) / 北京文本 五种版式；见进度日志 B–I |
| 3 | 天津政府采购网直采适配器 | owner 决策 | 需要境内 VPS / 反爬策略，沙箱做不了 |
| 4 | 法定窗口引擎 | **完成** `14cac81` | — |
| 5 | LATE_WINDOW 倒计时 / 地区偏好账号化 | 倒计时**完成**；账号化**未做** | 账号化需要 `api/_privateDb.js` `ensurePrivateSchema` 增加 `private_user_ui_preferences` 列迁移 → owner 决策 |
| 6 | 品牌×型号×参数 证据表 | **成交价部分完成** `0701bef` | 快照 `award_price_reference`（品牌×型号×单价原文，按设备类别归组）+ 商机池页「成交价参考」+ 详情页「同类设备近期成交参考」。"参数"部分仍依赖 PR #71 参数证据助手（未合并） |
| 7 | 微信 H5 准备 | owner 决策 | 需要公众号/小程序主体 |
| 8 | 分支 / PR 收敛 | owner 决策 | 30 个分支、7+ 个开放 PR，不代 owner 关闭 |

---

## 4. 明确不做 / 等 owner 决定的事

- 不合并任何 PR，不动 `main`，不关闭旧 PR / 删旧分支。
- 不买 VPS、不申请微信主体、不改数据库 schema（`private_user_ui_preferences`）。
- 不做 STOP 清单里的东西：中标概率、自动投标、CRM、报价、登录墙、联系人挖掘。
- 报告 §8 的 5 个 owner 决策项 owner 尚未回答（Route C 服务先行、定价锚、8 周冻结、Gate 设定、分支收敛）。

---

## 5. 踩过的坑（别再踩）

1. 可刷新的法定窗口数据**不能放进 `card.facts`**——`scripts/check-runtime-opportunity-time.mjs` 要求 refresh 后 `facts` 字节级一致。
2. 不要把节假日日历嵌到每张卡片里——会把快照撑到 1.85 MB，超过 runtime 缓存上限 1,945,600 B。用快照级 `working_calendar` + 卡片级紧凑项。
3. 任何改动快照输出的提交后，必须重跑 `python3 pipeline/scripts/refresh_bundled_snapshot.py`（cwd `web`），否则测试套件里"打包快照 vs 重建"的守卫会失败。
4. `validate_records` 要求 `schema_version "0.1"`、`source.source_id`，每个关键事实都要有 evidence；测试夹具照着 `tianjin_live_ccgp_records.json` 里的记录抄。
5. `src/types/public.ts` 末尾没有换行符——用 python 做文本替换时不要用 `}\n` 作锚点。
6. 报告里"天津 cap 12→200 + 直接启用中标类型"不可行：Vercel 队列 `maxDuration` 300 s，每次请求 4 s 延时，10 次搜索 + N 条详情必须 < 300 s（16 条 ≈ 160 s 名义值）。
7. 不要再加第二个调度器：`collector_incremental_scheduler.py` 已经是日内增量采集。
8. Vite 预览：`--host` 不够，e2b 预览域名会被拒 → 需要 `server.allowedHosts`；预览配置必须放在 `web/` 内（否则解析不到 `vite`）。

---

## 6. 进度日志（追加式，最新在最下面）

### 2026-09-29 · 会话 1（报告 + PR #73/#74）
- 见 §2。用户看完总结后说"继续"，随后说"按照你的思路做…保存好方便下一个 AI 接手"。
- 本文件创建于此时；后续每个里程碑追加在下面。


### 2026-09-29 · 会话 2 · 里程碑 A：发现并修复 CCGP `bidType` 映射错误（`99c548a`）
**怎么发现的**：做 §6 (2) 中标公告解析的侦察时，用 `search.ccgp.gov.cn/bxsearch` 实测各 `bidType`（天津，kw=医院）：
`bidType=8` 返回的全是**更正公告**，`7` 全是**中标公告**，`10` 全是**竞争性磋商公告**，`11` 成交公告，`12` 终止公告（路径 `/cggg/dfgg/fblbgg/`）。
仓库里的 `BID_TYPE_CODES` 是 `更正 6 / 磋商 7 / 中标 8 / 成交 9 / 终止 10` —— 全错（0–5 是对的）。

**后果（解释了两个长期现象）**：
1. 天津计划里的"竞争性磋商"查询实际查的是中标公告 → 被 `is_primary_opportunity_candidate` 过滤掉 → 库里 56 条天津记录全是公开招标公告，从来没有磋商记录（9 月天津仅 kw=医院 就有 11 条磋商公告）。
2. 活跃项目的更正/终止事件监视实际查的是"邀请公告"和"竞争性磋商" → `tianjin_notice_events.json` 一直是空的（9 月天津医院有 20+ 更正公告、14 条终止公告）。

**修复**：`ccgp_discovery.py` 的 `BID_TYPE_CODES` 改为 `0 全部 / 1 公开招标 / 2 询价 / 3 竞争性谈判 / 4 单一来源 / 5 资格预审 / 6 邀请公告 / 7 中标公告 / 8 更正公告 / 9 其他公告 / 10 竞争性磋商 / 11 成交公告 / 12 终止公告`；`PRIMARY_OPPORTUNITY_EXCLUSION_PATHS` 加 `/fblbgg/`。新增 3 个测试钉死映射。全套 782 通过。

**部署后要看什么**：`tianjin_sync_report.json` 里 `unique_discovered_candidate_count` 应明显上升（磋商开始进来）、`new_notice_event_count` > 0；`tianjin_notice_events.json` 不再为空；机会池开始出现 `notice_type = 竞争性磋商公告`。
**风险**：磋商适配器与事件解析器此前从未跑过真实流量，可能出现解析失败——都是 fail-closed（记入 failures，不发布假事实）；事件详情解析失败时回退为 discovery-only 事件（只压卡、不改事实）。

**验证来源**（fetch 于 2026-09-29，沙箱 curl 会被限频，用 fetch 工具）：
`https://search.ccgp.gov.cn/bxsearch?searchtype=1&page_index=1&bidSort=0&buyerName=&projectId=&pinMu=0&bidType=<N>&dbselect=bidx&kw=医院&start_time=2026:09:01&end_time=2026:09:29&timeType=6&displayZone=天津&zoneId=12&pppStatus=0&agentName=`

### 2026-09-29 · 会话 2 · 里程碑 B：中标/成交公告解析器（`39f5922`）
**新增** `web/pipeline/medical_channel_pipeline/ccgp_award.py`（parser + validator + merge + scope）与 `pipeline/tests/test_ccgp_award.py`（11 个测试，夹具在 `pipeline/tests/fixtures/ccgp_award_*.html`，均由真实 CCGP 页面裁剪而来，正文未改）。全套 793 通过。

**为什么是"独立记录类型"而不是事件**：中标结果承载的是新事实（供应商、金额、品牌/型号/单价），不是对既有机会的修饰；做成 `record_type = "AWARD_RESULT"`、`lifecycle_state = "AWARDED"` 的独立记录、独立存储（下一里程碑 `tianjin_award_records.json`），机会池只需按 `project_number` 关联即可。

**两种模板都覆盖**（真实页面结构记录如下，改解析器前先看这里）：
- 全国模板（`/cggg/dfgg/zbgg/`，如 CQS26A01493）：`一、项目号：` / `三、中标（成交）信息：` 是**文本块**（`包号：N` → `供应商名称：` → `供应商地址：` → `中标（成交）金额：…元`；废标包写 `废标（终止）原因：`）；`四、主要标的信息` 是每包一张表 `名称|品牌|规格型号|数量|单价`，且 `<th>` 直接挂在 `<table>` 下没有 `<tr>`（浏览器会自动补，解析器要自己补）。
- 天津分站镜像（三中心 535、五中心 589、一中心 921）：整个正文包在一个外层 `<table>` 的单元格里（嵌套表），`三、中标信息`/`三、成交信息` 后每包一张 `供应商名称|供应商地址|统一社会信用代码|企业办公电话|中标金额(万元)|评审得分` 表，随后是带 `排序` 列的评审报价表（要排除），`四、主要标的信息` 每包 `类型|名称|品牌|规格型号|数量|单价(万元)`；工程类标的表是 `类型|名称|施工范围|施工工期|项目经理|执业证书信息`。
- 解析器用**文档顺序的 block 模型**（文本块 / 表块）：外层含嵌套表的表被当作"布局包装"降级为文本流，最内层表才是数据表；`第N包 ：` / `包号：N` 文本块决定后续表属于哪个包。

**金额规则（fail-closed）**：只有在值里或列头里明确出现 `万元` 才 ×10000；`元` 按原值；没有单位 → `None`（不猜）。`total_amount_cny` 优先取公告概要 `总中标金额/总成交金额`（`amount_basis = SUMMARY_TOTAL`），否则各包求和（`PACKAGE_SUM`）。

**范围判断**：`is_medical_channel_relevant_award` 复用 `channel_scope`，并且**全部标的为 `工程类` 时直接排除**（否则"CT室、DR室改造项目"会因 CT/DR 缩写误判为医疗渠道相关）。

**已知局限**：`procurement_method` 在天津镜像页面上没有 → `None`（不推断）；只解析 HTML 正文，附件里的信息不看；`人民币大写` 不解析。

### 2026-09-29 · 会话 2 · 里程碑 C/D/E：中标结果全链路上线（`a5f0b4c` → `d52f1a4` → `f66654d`）
**设计决定（已实现）**：中标/成交结果 = **独立的规范记录类型** `AWARD_RESULT`（不是事件、不进机会池），独立存储 + 独立同步 + 独立运行时阶段；机会池只按 `project_number` 关联：有已发布结果的项目从池子里**退役**（`awarded_project_count`），公开快照多一个紧凑有界的 `award_ledger`（≤40 条，只含公开事实：供应商、各包金额、品牌/型号/单价、法定质疑窗口 `RESULT_CHALLENGE`、官网 `source_url`；地址/电话/统一社会信用代码留在规范存储不进快照）。

**文件地图**
- 同步脚本 `web/pipeline/scripts/sync_ccgp_awards.py`：计划 `pipeline/data/tianjin_award_query_plan.json`（天津/TJ 锁定，5 个关键词 × `中标公告`(bidType 7) + `成交公告`(11)，lookback 7 天，unseen-first，`max_details` 8，延时 4 s）；`--detail-url` 可重复，用于运营手工补录/回填（跳过搜索，不跳过解析）；`time_budget_seconds` 到点后不再发新请求（已验证的结果照常合并）。输出 `tianjin_award_records.json` + `tianjin_award_sync_report.json`（含 `out_of_scope`、`matched_pool_project_numbers`、`skipped`）。
- 快照：`public_snapshot.build_public_snapshot(records, as_of, notice_events, award_records)`；`publish_web_snapshot.py --award-input`（默认读天津 award 存储）；`refresh_bundled_snapshot.py` 自动读取；`combine_snapshots` 合并各市场 ledger（按 award_id 去重、最新在前、封顶）。
- 运行时：`collector_runtime.py` 新阶段 `award`（在 `event6` 之后、`tjmugh` 之前），缓存键 `CCGP_AWARDS_KEY`（v2 命名空间 `medicalchannelai:collector-ccgp-awards:v2`）。**这个阶段永远 COMPLETED**：任何异常/发布门禁关闭 → 结果 `status: DEGRADED`、旧存储原样保留（`award_store_carried_forward`），后续阶段不受影响；请求预算 `AWARD_STAGE_TIME_BUDGET_SECONDS = 200`。`_run_publish` 把 award 存储当**可选输入**（没有就空 ledger，不阻塞发布）。
- GitHub 兜底工作流 `.github/workflows/tianjin-medical-refresh.yml`：新增 award 同步步骤（`continue-on-error: true`），publish 加 `--award-input`，提交清单加两个 award 文件。
- 前端/API：`src/types/public.ts`（`PublicAwardLedgerEntry` 等）、`types/index.ts`、`StaticSnapshotTodayActionsService.ts`、`api/_privateCore.js`（today 响应透传 `awarded_project_count` / `award_ledger` / `working_calendar`）。**还没有 UI**（见下一步）。

**真实数据验证（2026-09-29 沙箱内实跑，非 mock）**
- 先用 `--detail-url` 对 4 个真实页面做种子（3 条入库，CT室/DR室改造工程类被范围过滤排除）。
- 然后完整计划实跑：9/10 查询成功（1 次超时），7 天窗口发现 **31 条**天津中标/成交公告，取 8 条详情，新增 4 条在范围内（药检院检测设备 汇像/岛津/梅特勒、中医一附院设备维保 3 包、东丽疾控 传染病监测设备 辉锦创兴 AutoPlex-12、中心妇产 液氮/医用气体），4 条被范围过滤（绿化养护、AI 急救实训平台、放射外科手术系统维保、**手术显微镜**）。合并后 7 条；与现有机会池匹配 3 个项目（泰达 腔镜 TJBHGP-2026-024、五中心 DSA XCSD-2026-A-589、中医一附院维保 ZCZBZC-GK-2026080547）→ 这 3 个项目在快照里退役为 AWARDED。用时 119 s。
- 顺带发现共享范围词表的**漏判**：`手术显微镜`、`放射外科手术系统` 不在词表 → 已加 contextual terms `显微镜 / 腔镜 / 手术系统`（需要医疗语境，避免高校生物显微镜误入）。重建打包快照后机会池 417 → **425**，新增 8 条全部是腔镜/孔镜/手术系统类设备招标（北医三院设备购置、秦皇岛三院椎间孔镜手术系统、宝泉岭医院腹腔镜、吉大二院胸腔镜、保定宫腔镜等）——这些此前一直被公开池漏掉。
- 打包快照压缩后 1,707,280 B（上限 1,945,600 B，余量 ~238 KB）。

**注意（沙箱 IP）**：这次 `search.ccgp.gov.cn` 从沙箱可以访问了（上一节里 curl 被限频），说明限频是间歇性的；仍然遵守 4 s 延时、每天一次，不要在沙箱里反复实跑。

**部署后要看什么**：`/api/collector-status` 里 `award` 阶段的 `result.status`（OK / DEGRADED）与 `new_award_record_count`；公开快照的 `awarded_project_count`、`award_ledger` 长度；`tianjin_award_sync_report.json` 的 `out_of_scope`（用来继续修词表）。

**下一步（按优先级）**：
1. §6 (6) 最小 UI：机会池页/首页加"最新中标结果"区块读取 `award_ledger`（供应商、金额、品牌/型号、质疑窗口倒计时、官网链接）；详情页对已退役项目显示"已中标：XX 公司 / 金额"。
2. 让 `sync_tianjin_plan.py` 的事件监视复用 award 存储：项目已中标时不必再查更正/终止（省请求预算）。
3. 词表：把 `tianjin_award_sync_report.json.out_of_scope` 作为每日词表回归输入。

### 2026-09-29 · 会话 2 · 里程碑 F：中标结果最小 UI + 单价合理性护栏（`7e1320b`）
- **UI**：`src/components/shared/AwardLedgerSection.tsx`，挂在商机池页（`OpportunityPoolPage`）列表下方："最新中标 / 成交结果"。每条：结果徽标（中标/成交/部分/全部包废标）、采购人、项目名、编号、总金额（注明"各包合计"还是公告总额）、每包供应商+金额（废标显示原因）、折叠的"品牌/型号/单价"、`RESULT_CHALLENGE` 质疑期倒计时（复用 `LegalWindowNotice`，仍带 94 号令免责）、官方公告链接。默认显示 5 条可展开；按用户业务地区过滤（`market_code`）；没有条目时整块不渲染。**没有胜率、没有推断**（页脚明示）。
- 数据通路：`verifiedOpportunityPool.getVerifiedOpportunityPool()` 新返回 `award_ledger`（客户端按 `working_calendar` 重算剩余工作日，`refreshAwardLedger`）和 `awarded_project_count`；`ApiTodayActionsService` 也透传（依赖 `api/_privateCore.js` 已加的三个键）。首页/详情页尚未展示（详情页"已中标：XX 公司"仍是待办）。
- 用 esbuild + `react-dom/server` 对真实 ledger 做了静态渲染核对（5 条 TJ、BJ-only 为空），顺手抓到一个**数据错误**：东丽疾控 `BJFHGJ-2026-038` 的标的单价渲染成 "312000 万元"——原公告表头写 `单价(万元)` 但单元格填的是元（312000，与包金额 ¥312,000 一致）。解析器按声明单位换算没有错，但结果荒谬。
- **护栏** `ccgp_award.reconcile_item_prices(items, packages, total)`：单价×数量不得超过所在包金额（无包金额则用公告总额）；超过时不信任声明单位——若按"元"读能放进包内就用元，否则置 `None`（宁缺毋滥）。已对存储中的该记录离线修正（不重新抓取），新增夹具 `ccgp_award_tianjin_unit_price_misdeclared.html`（真实页）+ 2 个测试。套件 **814**。
- 提醒：`quantity` 是自由文本（`1台`/`见附件`），护栏里解析不到数字按 1 计；`price/10000` 非整数时直接置 None。

**当前 PR #74 提交链**：`14cac81` → `dcae64f` → `99c548a` → `281a3ef` → `39f5922` → `cc1592f` → `a5f0b4c` → `d52f1a4` → `f66654d` → `1660930` → `7e1320b`（+ 本条交接提交）。全部在特性分支，`main` 未动，PR 仍是 Draft。

**给下一个 AI 的最短起手式**
```bash
cd /home/user/MedicalChannelAI && git status && git log --oneline -3
cd web/pipeline && python3 -m unittest discover -s tests | tail -3     # 期望 814 OK
cd .. && npm run build                                                 # prebuild + tsc + vite
```
若 `.git/config` 丢失：`git remote add origin https://github.com/wpuu/MedicalChannelAI.git`，`git config credential.helper 'store --file=/home/user/.git-credentials-mca'`，`git config user.name/email`，`git config core.fileMode false`。

### 2026-09-29 · 会话 3 · 里程碑 G/H：跟进×中标结果、项目编号归一化、事件监视省预算（`9f6680a`、`7d0aa7e`）
- **G1 项目编号归一化**：池子里 ~1.4% 的项目编号带全角括号/破折号（`HBHX（Z）-2026-019`），结果公告常用半角 → 永远匹配不上。新增 `ccgp_award.normalize_project_number`（全角→半角、去空白、小写），用于 中标↔机会池 退役匹配、同步报告的 `matched_pool_project_numbers`；前端镜像 `src/utils/projectNumber.ts`。事件匹配（更正/终止）**没动**，仍是 `strip().lower()`。
- **G2 跟进页 / 详情页显示中标结果**：`AwardResultNotice`（完整块：各包供应商+金额、质疑期倒计时、官方链接、明示"不会自动改你的跟进状态"；紧凑行：我的跟进列表项）。数据来自 `verifiedOpportunityPool.getAwardLedger()`（走去重的快照客户端，ETag 复用；API 模式下也是拉公开快照，不新增函数——Vercel 函数数 11/12 已接近上限，**不要**为此加 endpoint）。匹配用 `findAwardForProject`。
- **H 事件监视跳过已中标项目**：`exclude_awarded_projects(watch, awards, as_of)`；Vercel `_run_ccgp` 用前一天的 award 存储（`_cached_list(CCGP_AWARDS_KEY)`，无缓存时从打包文件引导），`sync_tianjin_plan.py` 新参数 `--existing-awards-input`（默认打包存储）。两处都在 cap 检查**之前**排除并输出 `event_watch_skipped_awarded`。以天津当前数据算，省 3 个项目 × 2 次搜索/天，也减少了 `EVENT_WATCH_ALL_SEARCHES_FAILED` 的暴露面。
- 套件 **818**；`npm run build` 通过。用 esbuild+react-dom/server 对真实 ledger 静态渲染核对过两个组件。

**待办（顺序建议）**：① 区域（京冀辽吉黑）中标同步：`sync_ccgp_awards.py` 目前计划锁单一 `market_code`，运行时 award 阶段预算 200 s 只够天津；扩到区域应放在自托管 `regional-medical-refresh.yml`（无 300 s 限制）逐省跑 + publish 合并 ledger（`combine_snapshots` 已支持多市场 ledger 去重）。② `formatBudget` 对 10,499,940 显示 "1050.0 万元"（toFixed(1) 的进位），可改成保留两位或整万取整。③ 事件匹配也可以改用 `normalize_project_number`（需同步改 `_build_event_states`）。

### 2026-09-29 · 会话 3 · 里程碑 I：五省中标/成交同步 + 市场隔离（`53eb87c`）
- **同步**：`scripts/sync_regional_awards.py` + `data/regional_award_query_plan.json`（BJ/HE/LN/JL/HL 逐省串行，每省 5 关键词 × 中标/成交 = 10 次搜索、≤6 篇详情、240 s 预算，省间 4 s；每日共 50 次搜索）。复用 `sync_ccgp_awards.run_award_sync`，新增 `load_plan(path, market_code=)` 覆盖与 `--market-code`。**地理护栏**：搜索行 `地域` 必须经 `candidate_market_code` 映射到计划市场，否则丢弃并记入 `region_mismatch_count/region_mismatches`（详情页 `facts.region` 只是区县，不能证明省份）。定向 `--detail-url` 不走护栏。
- **存储/发布**：`data/regional_award_records.json`（合并存储，`facts.market_code` 标市场）+ `data/regional_award_sync_report.json`（`markets{code}` 为每省 TJ 同款报告 + 汇总键）。`publish_web_snapshot.py` / `refresh_bundled_snapshot.py` 默认读两份存储并 `split_awards_by_market` → 天津 builder 只见天津 award，区域 builder 只见区域 award；ledger 合并去重、上限 40。退役键改为 `(market_code|None, normalize_project_number)`（`awarded_project_keys` / `is_awarded_project`；旧的无 market 记录匹配任意市场）。
- **运行时**：`collector_runtime._bundled_award_records()` 读两份打包存储引导；`_run_award` 每轮把打包的区域 award 并入存储（区域不在运行时同步，靠部署包带过去），报告多一键 `bundled_regional_awards_added`。
- **工作流**：`regional-medical-refresh.yml` 在区域机会同步后加 "Sync verified regional CCGP award/deal results"（`continue-on-error`），提交清单 + `paths:` 触发加了两份文件，单测子集加 `test_ccgp_award`/`test_regional_award_sync`；`tianjin-medical-refresh.yml` 发布步骤**去掉**了 `--award-input`（走默认双存储，否则两条工作流会来回覆盖 ledger）。`publish_generated_data_github.py` 对缺文件会 `GENERATED_FILE_MISSING` → 已把种子文件提交进仓库。
- **解析器（真实页面驱动，全部有 fixture + 测试）**：
  - 河北：中标信息表 `供应商名称|供应商地址|供应商编码` 无金额 → `_is_supplier_table` 接受身份列；主要标的表上方有跨列 `货物类/服务类` 行 → `_table_header` 定位真表头并作默认 `category`；金额在标的表 `中标金额` 列且**无单位** → `UNITLESS_YUAN_FLOOR=100000`（万元读法 ≥10 亿才按元读，更小的仍拒绝）；`_backfill_package_amounts`（同一供应商唯一包时按标的表回填，`amount_source: ITEM_TABLE`）；服务类表 `服务范围/服务要求/…` 也算标的表。
  - 黑龙江：`三、采购结果` + `合同包1(…)：` + 表头 `品目号|品目名称|采购标的|品牌|规格型号|数量（单位）|单价(元)|总价(元)` → `_RESULT_SECTION_RE` 放宽、`_package_no_from_text` 认 `合同包N`/`包组编号`、标的名取 `采购标的`、`品目名称` 作 category。
  - 辽宁：文本模板 `包组编号：002 / 结果类型：废标 / 废标情形：…` → 全包废标记录，`total_amount_cny` 置 None。
  - 北京（中央）文本模板：`中标（成交）金额：182.0000000（万元）`（单位在括号里）；标的表首个"名称"列是供应商 → `_item_name_index` 排除 供应商/采购人/代理/品目名称。
  - 概要 `中标金额 = 0` 视为未公布（大庆 HPV 检测服务按次计价）。
- **种子数据（2026-09-29 沙箱实跑）**：14 条真实区域 award（BJ 3 / HE 3 / JL 3 / HL 5；辽宁本周发现的 6 条全部超出医疗渠道范围）。打包快照 ledger 7→21、退役 3→4、池子仍 425、压缩后 1,726,992 B（上限 1,945,600）。运行日志：北京 10/10 搜索成功；河北 1–2 次搜索超时（`search.ccgp.gov.cn` 间歇限流）；`region_mismatch` 1（河北一行无 `地域`）。
- **UI**：`AwardLedgerSection` 每条加省份徽章（`ENABLED_MARKETS`）；已有的 `marketCodes` 过滤让用户地区偏好决定看哪些省的结果。
- 套件 **830**；`npm run build` 通过。

**待办（顺序建议）**：① `formatBudget` 对 10,499,940 显示 "1050.0 万元"（toFixed(1) 进位），改保留两位或整万取整。② 事件匹配改用 `normalize_project_number`（`_build_event_states`）。③ 品牌×型号×单价 证据表页面（§6 (6)）：数据已在 `award_ledger[].items`，先做按品牌/型号聚合的只读表。④ 观察首个自托管区域工作流日志：`regional_award_sync_report.json` 的 `failure_count`/`region_mismatch_count`，辽宁若持续 `CCGP_AWARD_SUPPLIER_NOT_FOUND` 需要再补一版辽宁中标（非废标）模板 fixture。

### 2026-09-29 · 会话 3 · 里程碑 J：成交价参考（品牌×型号×单价证据表）+ 两个小修（`0701bef`）
- **设备类别表** `data/device_families.json`（24 个粗粒度类别，有序、先匹配先赢；缩写按整词匹配，`CT` 不会命中 `CBCT`；维保/试剂/信息化/消毒供应排最前，口腔/核医学排在 CT 前）+ `medical_channel_pipeline/device_families.py`（`device_family_for_name`、`device_families_payload`）+ TS 镜像 `src/utils/deviceFamily.ts`。类别表随快照下发（`award_price_reference.families`），前端用同一张表给机会的 `标的` 归类。40 条 `parity_vectors` 同时被 Python 测试和 prebuild 门禁 `scripts/check-device-family-parity.mjs`（用 vite 的 esbuild 现场转译 TS）断言；门禁还核对快照里每一行的 `family` 与前端分类一致。**只用于展示归组，绝不进 scope / 排序 / actionability。**
- **快照新键** `award_price_reference {schema_version, lookback_days 365, max_rows 200, row_count, truncated, family_row_counts, families[], rows[]}`；行 = 一条结果公告里"单一品牌 + 可解析单价"的标的行 `{award_id, market_code, published_at, buyer_name, project_number, family, name, brand, model, quantity, unit_price_cny, line_count, source_url}`。多值单元格（`；`/`、`/`其他详见附件`/`等`）不归属、直接跳过；同一公告完全相同的行折叠为一行 `line_count`（黑龙江每台一行）。发布端 `combine_award_price_references` 去重合并；私有 today API 原样透传。当前 44 行 / 13 个类别，压缩后快照 1,752,528 B。
- **UI**：`AwardPriceReferenceSection`（商机池页 ledger 下方：类别 chips + 关键词框，关键词也匹配类别名所以搜"彩超"能命中"彩色多普勒超声诊断仪"；按业务地区过滤；每行带官方公告链接；默认 8 行可展开）；`AwardPriceReferenceNotice`（详情页：机会 `products[].name`（无则项目名）归类 → 同类别的行，跨六个市场，明示"类别相同不代表配置相同"）。数据都走 `getAwardPriceReference()`（复用去重快照客户端，不新增 Vercel 函数）。
- ledger 的 `items[]` 新增 `category`（河北 货物类/服务类、黑龙江 品目名称）。
- **小修**：事件匹配（更正/终止）改用 `normalize_project_number`（`_build_event_states` 与池侧匹配两处，`test_ccgp_events` 加全角编号用例）；`formatBudget` 改两位小数不进位（10,499,940 → "1049.99 万元"）。
- 套件 **839**；`npm run build` 通过（含新门禁）；用 esbuild + react-dom/server 对真实快照静态渲染核对过两个组件（彩超机会 → 7 行同类成交；无匹配/无数据时不渲染）。

**待办（顺序建议）**：① 首个自托管区域工作流运行后看 `regional_award_sync_report.json`（辽宁若持续 `CCGP_AWARD_SUPPLIER_NOT_FOUND` 需补辽宁中标模板 fixture）。② 类别表长尾：池内 1,485 个标的名约 60% 能归类，未归类多为耗材/实验室小件，按需往 `device_families.json` 加关键词（改完跑 Python 套件 + `node scripts/check-device-family-parity.mjs`）。③ "参数"维度：等 PR #71 参数证据助手合并后，把 `award_price_reference` 行接到参数对照表旁边。④ 成交价参考若要给"我的跟进"页也用，直接复用 `relatedReferenceRows(card, reference)`。

