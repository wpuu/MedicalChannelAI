# MedicalChannelAI 当前状态

日期：2026-08-31  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`DETERMINISTIC + REAL_PUBLIC + BACKUP/RESTORE + FULL CUSTOMER CHAIN GATES PASS / REAL HOST EXECUTION PENDING`  
生产就绪：**false**  
Draft PR：**#1（保持 Draft，不合并）**

## 当前可信验证基线

最新代码门禁证据：`9e747b05921317aaba9ac49b283645ac409d45be`  
Vercel deployment：`dpl_DnF6nf139xeWmXN9BEazRdx8eH63` → **READY**

同一提交实际执行：

- **508 个 Python unittest → OK**；
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
- **94 个 deterministic test modules**；
- **508 个实际执行 unittest cases**；
- 真实医疗附件 binary capture：0；
- Agnes benchmark：28 case，尚未真实执行；
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

新增：

```text
tools/medical_pilot/pilot_full_chain_smoke.py
tools/medical_pilot/test_pilot_full_chain_smoke.py
```

这不是单独调用 Agnes 的假 smoke，而是使用正式 runtime：

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

确定性门禁同时验证：

- 未登记 taxonomy classifier 不能偷偷进入匹配；
- smoke 必须使用已准入的 `HUMAN_CONFIRMED` classifier；
- 非 grounded model output 会进入 `MODEL_OUTPUT_REJECTED`，不会伪装 READY；
- public result 不回显 invite/session/tenant/profile/task/lease/model input；
- provider exception message 不进入安全输出。

当前只能宣称**完整业务链的确定性代码路径 PASS**；因为目标主机尚未配置并真实调用 Agnes，所以 `real_authenticated_end_to_end_smoke_passed=false`。

## 真实 Agnes 状态

已经具备：server-only Key、`agnes-2.5-flash` constrained contract、persistent queue / Worker / terminal result、shared global lease、grounded Today Actions / outreach，以及完整客户链 smoke。

但真实 authenticated Agnes provider 尚未在目标 Pilot 主机 PASS，因此不能声称“真实 Agnes 已跑通”。

## 统一真实 Pilot 主机验收已升级

核心：

```text
tools/medical_pilot/pilot_host_preflight.py
tools/medical_pilot/pilot_host_acceptance.py
deploy/pilot-host-acceptance-v0.1.json
deploy/medical-pilot-acceptance.service
deploy/PILOT_HOST_ACCEPTANCE.md
```

API / Worker systemd unit 强制 `/etc/medicalchannelai/pilot.env`，并在启动前 fail-closed preflight。

域名就绪后，目标主机运行：

```bash
sudo systemctl start medical-pilot-acceptance.service
sudo journalctl -u medical-pilot-acceptance.service -n 50 --no-pager
```

验收链现在是：

```text
真实主机配置/DB路径 preflight
→ 临时 SQLite 5条官方 bootstrap（必须5/5）
→ 真实天津附件 bytes/MIME/SHA/parser
→ 完整合成客户链：INVITED → Session → Profile → AWAITING_MODEL
  → persistent queue → global lease → real Agnes → Worker READY → Today READY
```

完整 acceptance 只进行**一次真实 Agnes provider 调用**，不再额外重复 provider-only smoke。

四项全部 PASS 才允许进入真实 Pilot 启动阶段。Acceptance 不写生产 DB，也不读取老杨资料。

## 备份 / 恢复闭环

核心：

```text
tools/medical_pilot/pilot_backup.py
tools/medical_pilot/pilot_restore.py
tools/medical_pilot/pilot_backup_job.py
deploy/medical-pilot-backup.service
deploy/medical-pilot-backup.timer
deploy/PILOT_BACKUP_RESTORE.md
```

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

当前域名未完成，所以以下真实主机步骤暂不执行：

1. 域名完成后，配置真实 canonical HTTPS origin；
2. 创建 `medicalai`、`/srv/medical/data`、`/srv/medical/backups`；
3. 创建 root-only `/etc/medicalchannelai/pilot.env`；
4. 安装 Pilot/Worker/Acceptance systemd unit；
5. **先运行 `medical-pilot-acceptance.service`，overall PASS 才继续**；
6. 把5条官方项目正式导入 `/srv/medical/data/pilot.sqlite`；
7. 启动 `medical-pilot.service` + `medical-agnes-worker.service`；
8. 验证本机 health、生产库真实 queue → Agnes → READY；
9. 手工运行一次 `pilot_backup_job`，确认 backup + restore smoke PASS，再 enable timer；
10. 之后才创建老杨 INVITED 账号并发送一次性注册链接；
11. 完成 authenticated followup/reminder/followed/outreach、大陆/微信访问验收后，才评估 production_ready / merge。

## 仍然不能宣称

```text
production_ready=false
real_authenticated_agnes_provider_pass=false
real_attachment_binary_capture_count=0
real_host_backup_restore_smoke_pass=false
PR #1 = Draft / do not merge
```
