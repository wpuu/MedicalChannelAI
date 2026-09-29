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
| 测试基线 | `web/pipeline` Python 套件 **778 通过**（`14cac81` 后 773，`dcae64f` 后 778）；`npm run build` 全绿 |
| 用户指令 | "按照你的思路做，我相信你，每次过程和结果都保存好，方便下一个 AI 接手" |

---

## 1. 环境恢复（每个新会话先做）

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
| 2 | 中标公告解析 → 品牌/型号/金额 + AWARDED 生命周期 | **进行中**（见进度日志） | — |
| 3 | 天津政府采购网直采适配器 | owner 决策 | 需要境内 VPS / 反爬策略，沙箱做不了 |
| 4 | 法定窗口引擎 | **完成** `14cac81` | — |
| 5 | LATE_WINDOW 倒计时 / 地区偏好账号化 | 倒计时**完成**；账号化**未做** | 账号化需要 `api/_privateDb.js` `ensurePrivateSchema` 增加 `private_user_ui_preferences` 列迁移 → owner 决策 |
| 6 | 品牌×型号×参数 证据表 | 未开始 | 依赖 (2) 的中标解析输出 |
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
