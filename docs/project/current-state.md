# MedicalChannelAI 当前状态

日期：2026-08-31  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`DETERMINISTIC + REAL_PUBLIC + BACKUP/RESTORE GATES PASS / REAL HOST EXECUTION PENDING`  
生产就绪：**false**  
Draft PR：**#1（保持 Draft，不合并）**

## 当前可信验证基线

最新代码门禁证据：`6e7ab64c56df34be7e0881dc6d121f937e1e598b`  
Vercel deployment：`dpl_6gzgNNVv3AXMGYbp277Jj8tZ12PE` → **READY**

同一提交实际执行：

- **503 个 Python unittest → OK**；
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
- **93 个 deterministic test modules**；
- **503 个实际执行 unittest cases**；
- 真实医疗附件 binary capture：0；
- Agnes benchmark：28 case，尚未真实执行；
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`。

## 当前商务 Demo

```text
https://medicalchannelai.vercel.app
```

公开采购事实/官方链接是真实的；客户画像资源为明确演示数据；它不是老杨真实账号，也不是实时 Agnes。

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

## 真实 Agnes 状态

已经具备：server-only Key、`agnes-2.5-flash` constrained contract、persistent queue / Worker / terminal result、shared global lease、grounded Today Actions / outreach、synthetic provider smoke。

但真实 authenticated Agnes provider 尚未在目标 Pilot 主机 PASS，因此不能声称“真实 Agnes 已跑通”。

## 统一真实 Pilot 主机验收

核心：

```text
tools/medical_pilot/pilot_host_preflight.py
tools/medical_pilot/pilot_host_acceptance.py
deploy/pilot-host-acceptance-v0.1.json
deploy/medical-pilot-acceptance.service
deploy/PILOT_HOST_ACCEPTANCE.md
```

API / Worker systemd unit 强制 `/etc/medicalchannelai/pilot.env`，并在启动前 fail-closed preflight。

目标主机先运行：

```bash
sudo systemctl start medical-pilot-acceptance.service
sudo journalctl -u medical-pilot-acceptance.service -n 50 --no-pager
```

验收链：

```text
真实主机配置/DB路径 preflight
→ 临时 SQLite 5条官方 bootstrap（必须5/5）
→ 真实天津附件 bytes/MIME/SHA/parser
→ 合成 grounded input 的真实 Agnes authenticated contract smoke
```

四项全部 PASS 才允许进入真实 Pilot 启动阶段。Acceptance 不写生产 DB，也不读取老杨资料。

## 新增：备份 / 恢复闭环

核心：

```text
tools/medical_pilot/pilot_backup.py
tools/medical_pilot/pilot_restore.py
tools/medical_pilot/pilot_backup_job.py
deploy/medical-pilot-backup.service
deploy/medical-pilot-backup.timer
deploy/PILOT_BACKUP_RESTORE.md
```

### 在线备份

不再允许把运行中的 `pilot.sqlite` 直接 `cp` 当正式备份。

当前使用 SQLite Backup API：

- 源库只读连接；
- 能捕获已提交但仍在 WAL 中的页面；
- 目标临时文件完成后再原子落盘；
- 文件固定 `0600`；
- `integrity_check=PASS`；
- `foreign_key_check=PASS`；
- SHA-256；
- 只清理受控命名的历史备份。

真实测试已经在 writer 连接**保持打开**、WAL 文件仍存在时插入并 commit 新记录，然后在线备份；恢复后的 standalone SQLite 能读到该记录。因此 WAL 在线备份能力已有真实 unittest 执行证据。

### 恢复验证

每次正式备份任务不是“文件生成就算成功”，而是：

```text
create consistent backup
→ verify backup
→ restore into temporary isolated SQLite
→ integrity / foreign-key check
→ remove temporary candidate
```

只有 `restore_smoke=PASS` 才算本次 scheduled backup 成功。

恢复工具永远不会自动覆盖生产 `/srv/medical/data/pilot.sqlite`。真正灾难恢复必须：停止 API + Worker → 验证备份 → 生成独立 restore candidate → 人工保留原 DB/WAL/SHM → 提升 candidate → 再做业务 smoke。

### 自动计划

```text
每天 03:40 Asia/Shanghai
随机延迟最多300秒
Persistent=true
保留14份
```

备份目录 `/srv/medical/backups` 必须 medicalai-only；每份备份包含真实客户数据，按生产敏感数据保护。

## 真实服务器后的固定顺序

1. 部署代码/H5，创建 `medicalai`、`/srv/medical/data`、`/srv/medical/backups`；
2. 创建 root-only `/etc/medicalchannelai/pilot.env`；
3. 安装 Pilot/Worker/Acceptance systemd unit；
4. **先运行 `medical-pilot-acceptance.service`，overall PASS 才继续**；
5. 把5条官方项目正式导入 `/srv/medical/data/pilot.sqlite`；
6. 启动 `medical-pilot.service` + `medical-agnes-worker.service`；
7. 验证本机 health、真实 queue → Agnes → READY；
8. 手工运行一次 `pilot_backup_job`，确认 backup + restore smoke PASS，再 enable `medical-pilot-backup.timer`；
9. 再运行隔离的完整 invite/profile → Today queue → real Agnes → READY smoke；
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
