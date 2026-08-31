# MedicalChannelAI 当前状态

日期：2026-08-31  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`DETERMINISTIC + REAL_PUBLIC + BACKUP/RESTORE + FULL CUSTOMER CHAIN + AGNES BENCHMARK/REVIEW GATES PASS / REAL HOST EXECUTION PENDING`  
生产就绪：**false**  
Draft PR：**#1（保持 Draft，不合并）**

## 当前可信验证基线

最新代码门禁证据：`42caf97cb7609aa96acf54fec4cd895509eecee5`  
Vercel deployment：`dpl_DjRWgbYHQYkZ2N9XEitzefMkBthh` → **READY**

同一提交实际执行：

- **530 个 Python unittest → OK**；
- `npx tsc --noEmit` → PASS；
- Vite production build → PASS；
- 1887 modules transformed；
- `dist/index.html` 约 413.58 KiB / gzip 127.17 KiB。

GitHub Actions 仍存在 runner 未分配问题，因此开发分支继续使用 Vercel Preview 作为可信执行门。

## 当前规模

- 7 个运行时 P0 Source：4 IMPLEMENTED、3 PARTIAL_IMPLEMENTATION；
- 自动 listing discovery：2/7 ready；
- 50 条 VERIFIED 天津商机 regression fixtures；
- 15 条 Institution Evidence；
- 41 份 Schema/合同；
- **96 个 deterministic test modules**；
- **530 个实际执行 unittest cases**；
- 真实医疗附件 binary capture：0；
- Agnes benchmark：**12 general + 16 taxonomy = 28 case，尚未真实执行**；
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`。

## 当前商务 Demo

```text
https://medicalchannelai.vercel.app
```

公开采购事实/官方链接是真实的；客户画像资源为明确演示数据；它不是老杨真实账号，也不是实时 Agnes。

真实 Pilot canonical domain 由用户另行处理，本阶段不继续做域名配置。域名完成后再接入 host acceptance / Caddy / Cookie / same-origin 验收。

## 真实公开数据链

5条冻结官方天津项目已经在隔离 live 环境真实执行：

```text
input=5
success=5
failure=0
```

CCGP `采购需求` 表格已经进入 VERIFIED `product_item` grounding。`XCSD-2026-C-181 / 病原微生物能力提升相关设备购置` 已真实得到：

- `LAB_NGS_SEQUENCER`
- `LAB_AUTOMATED_LIBRARY_PREP`
- `LAB_METAGENOMICS_ANALYSIS`
- `LAB_MICROBIAL_MASS_SPECTROMETRY`
- `LAB_BIOINFORMATICS_COMPUTE_APPLIANCE`

这些 controlled taxonomy ID 已同步进入 `/profile` 产品能力选择。

## 真实附件状态

`XCSD-2026-C-181项目需求书.docx` 的天津财政官方下载 URL 已被冻结到 `deploy/pilot-host-acceptance-v0.1.json`。

Vercel IAD 两次真实下载分别约20秒、60秒 read timeout，因此当前继续保持：

```text
real attachment bytes = 0
MIME/size/SHA-256 = 未观察
real OOXML parser = 未在该真实附件上 PASS
```

不把“官方 URL 已确认”解释成“附件 binary 已验证”。

## 完整隔离客户链 smoke：代码级 PASS

核心：

```text
tools/medical_pilot/pilot_full_chain_smoke.py
tools/medical_pilot/test_pilot_full_chain_smoke.py
```

正式路径被实际单元测试覆盖为：

```text
临时 SQLite
→ 合成客户 Profile + 合成 VERIFIED 商机/证据
→ INVITED account
→ POST /auth/redeem
→ opaque Session Cookie
→ invite replay 401
→ PUT /profile
→ profile personalized ready
→ after_save 自动 Today refresh
→ Today = AWAITING_MODEL
→ SQLite persistent dispatch queue = 1 task
→ shared global Agnes lease
→ 正式 queue worker
→ validated terminal result = READY
→ queue drained
→ 再 GET /today
→ terminal result reuse
→ Today = READY + rendered decision
```

所有客户、商机、关系、证据都是明确 `SYNTHETIC` 合成数据；临时 SQLite 在执行后删除。不读取老杨资料，不写生产 DB。

当前只能宣称**完整业务链的确定性代码路径 PASS**；因为目标主机尚未配置并真实调用 Agnes，所以 `real_authenticated_end_to_end_smoke_passed=false`。

## Agnes 28-case benchmark + 只读准入审核 gate 已完成代码准备

固定题库仍是原来的两组：

```text
12 case：agnes-2.5-flash-v0.1.json
16 case：agnes-2.5-flash-product-taxonomy-v0.1.json
合计：28 case
```

没有改题目或降低评分门槛。

统一真实执行器与运维入口：

```text
tools/medical_pilot/agnes_benchmark_suite.py
deploy/medical-agnes-benchmark.service
deploy/AGNES_BENCHMARK.md
```

当前安全边界：

- 模型固定 `agnes-2.5-flash`；
- base URL 必须通过 Agnes 官方 `/v1` allowlist；
- Key 只读取 `MCAI_AGNES_API_KEY`，不写 repo；
- **每一次 provider start 都先取得 shared global lease**；
- 单 case provider retry 固定 0，不能在一个 lease 下偷偷重试；
- API/Worker 必须处于维护窗口，业务 queue 必须为空；
- 每个 case 开始前重新检查业务 queue，客户任务出现时 benchmark 会 fail-closed；
- 两个旧 standalone benchmark 的直接 `--execute` 已禁用；
- 结果文件默认 `/srv/medical/data/agnes-benchmark-result-v0.1.json`，`0600`，拒绝静默覆盖；
- benchmark 结果绑定执行时的 `general_manifest_sha256`、`taxonomy_manifest_sha256`、`classifier_registry_sha256_before/after`；
- 执行过程中题库或 registry 发生变化，benchmark 不能 PASS；
- 即使 28-case 全 PASS，也只返回 `ELIGIBLE_FOR_MANUAL_ADMISSION_REVIEW`。

新增只读准入审核器：

```text
tools/medical_pilot/agnes_benchmark_review.py
```

审核器重新验证：

- 结果文件为普通文件、非 symlink、严格 `0600`；
- 28/28、28 provider starts、两个 aggregate PASS、无 case failure；
- global lease / maintenance / quiescent queue / retry=0；
- 当前两份 benchmark manifest SHA-256 与执行结果完全一致；
- 当前 classifier registry SHA-256 与 benchmark 执行前/后记录完全一致；
- 当前 classifier 仍为 `BENCHMARK_PENDING / can_drive_matching=false`。

只有全部成立才返回：

```text
ELIGIBLE_FOR_MANUAL_REGISTRY_CHANGE
registry_change_performed=false
automatic_classifier_admission_allowed=false
OWNER_REVIEW_REQUIRED_BEFORE_EXPLICIT_REGISTRY_COMMIT
```

审核器**永远不改 registry**。后续若决定准入，仍必须有明确 Owner 人工决策，并通过单独可审查的 Git commit 显式修改 registry。

当前事实仍然是：

```text
agnes_benchmark_executed=false
agnes_classifier_status=BENCHMARK_PENDING
agnes_classifier_can_drive_matching=false
```

不能把“执行器/审核器代码 PASS”写成“真实 Agnes benchmark PASS”或“classifier 已准入”。

## 真实 Agnes / Host Acceptance 状态

真实 authenticated Agnes provider 仍未在目标 Pilot 主机 PASS，因此不能声称“真实 Agnes 已跑通”。

域名就绪后，目标主机先运行：

```bash
sudo systemctl start medical-pilot-acceptance.service
sudo journalctl -u medical-pilot-acceptance.service -n 50 --no-pager
```

Host Acceptance 链：

```text
真实主机配置/DB路径 preflight
→ 临时 SQLite 5条官方 bootstrap（必须5/5）
→ 真实天津附件 bytes/MIME/SHA/parser
→ 完整合成客户链：INVITED → Session → Profile → AWAITING_MODEL
  → persistent queue → global lease → real Agnes → Worker READY → Today READY
```

完整 acceptance 只进行**一次真实 Agnes provider 调用**，不额外重复 provider-only smoke。四项全部 PASS 才允许进入真实 Pilot 启动阶段。

## 备份 / 恢复闭环

正式备份使用 SQLite Backup API，不直接 `cp` 运行中的 WAL 数据库。已经实际测试 writer 连接保持打开、WAL 文件仍存在时，备份能够读取已提交记录。

每次 scheduled backup 必须同时通过：

```text
backup integrity_check
→ foreign_key_check
→ SHA-256 / 0600
→ temporary restore candidate
→ restore smoke
```

每天 03:40 Asia/Shanghai + 最多300秒随机延迟，保留14份。工具永远不会自动覆盖生产库。

## 真实服务器后的固定顺序

当前域名未完成，所以域名相关步骤暂不执行。非域名依赖的 benchmark 执行器和只读审核器已准备完毕，但真实 benchmark 仍要求目标主机环境和 Key。

后续顺序：

1. 目标主机环境文件准备后，在维护窗口运行一次 28-case Agnes benchmark；
2. 对结果运行 `agnes_benchmark_review`，只获得人工准入审核资格，不自动启用 classifier；
3. 域名完成后配置真实 canonical HTTPS origin；
4. 创建 `medicalai`、`/srv/medical/data`、`/srv/medical/backups`；
5. 创建 root-only `/etc/medicalchannelai/pilot.env`；
6. 安装 Pilot/Worker/Acceptance systemd unit；
7. **先运行 `medical-pilot-acceptance.service`，overall PASS 才继续**；
8. 把5条官方项目正式导入 `/srv/medical/data/pilot.sqlite`；
9. 启动 `medical-pilot.service` + `medical-agnes-worker.service`；
10. 验证本机 health、生产库真实 queue → Agnes → READY；
11. 手工运行一次 `pilot_backup_job`，确认 backup + restore smoke PASS，再 enable timer；
12. 之后才创建老杨 INVITED 账号并发送一次性注册链接；
13. 完成 authenticated followup/reminder/followed/outreach、大陆/微信访问验收后，才评估 production_ready / merge。

## 仍然不能宣称

```text
production_ready=false
real_authenticated_agnes_provider_pass=false
agnes_benchmark_executed=false
agnes_classifier_status=BENCHMARK_PENDING
real_attachment_binary_capture_count=0
real_host_backup_restore_smoke_pass=false
PR #1 = Draft / do not merge
```
