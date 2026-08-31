# MedicalChannelAI Pilot Backup / Restore

Status: `REQUIRED_FOR_TIANJIN_PILOT_2026-08-31`

目标：在单机 SQLite Pilot 下做到**在线一致备份、每天自动验证可恢复、恢复时不直接覆盖生产库**。

## 1. 为什么不能直接 cp pilot.sqlite

Pilot 使用 SQLite/WAL。运行中直接复制 `pilot.sqlite` 可能漏掉已经提交但仍位于 WAL 的页面。

正式备份必须使用：

```text
sqlite3.Connection.backup()
```

当前实现：

```text
tools.medical_pilot.pilot_backup
tools.medical_pilot.pilot_restore
tools.medical_pilot.pilot_backup_job
```

源库以只读连接打开；SQLite Backup API 负责生成一致 standalone SQLite，不依赖复制 `-wal` / `-shm` 文件。

## 2. 备份目录

真实主机创建：

```bash
sudo install -d -o medicalai -g medicalai -m 700 /srv/medical/backups
```

备份文件固定 `0600`，其中包含真实客户资料，视为敏感生产数据。禁止上传 GitHub、公开对象存储、聊天记录或普通共享盘。

## 3. 手工执行一次“备份 + 恢复证明”

```bash
cd /srv/medical/app
sudo -u medicalai python3 -m tools.medical_pilot.pilot_backup_job \
  --db /srv/medical/data/pilot.sqlite \
  --out-dir /srv/medical/backups \
  --keep 14
```

一个任务包含：

```text
在线 SQLite Backup API
→ source integrity_check
→ backup integrity_check
→ foreign_key_check
→ fsync + 原子落盘
→ 0600
→ 临时目录 prepare restore candidate
→ candidate integrity_check / foreign_key_check
→ 删除临时 candidate
```

只有最终 `status=PASS` 且 `restore_smoke=PASS` 才算一次有效备份任务。

安全输出只包含文件名、大小、SHA-256、检查状态、保留数量；不输出表内容或客户值。

## 4. 自动每日备份

安装：

```bash
sudo cp deploy/medical-pilot-backup.service /etc/systemd/system/
sudo cp deploy/medical-pilot-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now medical-pilot-backup.timer
```

计划：

```text
每天 03:40 Asia/Shanghai
+ 最多 5 分钟随机延迟
Persistent=true
保留最近 14 份
```

查看：

```bash
systemctl list-timers medical-pilot-backup.timer --all
sudo systemctl status medical-pilot-backup.timer --no-pager
sudo journalctl -u medical-pilot-backup.service -n 50 --no-pager
```

Timer 不做生产恢复，只做备份 + 临时 restore smoke。

## 5. 单独验证某份备份

```bash
cd /srv/medical/app
sudo -u medicalai python3 -m tools.medical_pilot.pilot_restore verify \
  --backup /srv/medical/backups/pilot-YYYYMMDDTHHMMSSZ.sqlite
```

要求：

```text
status=PASS
integrity_check=PASS
foreign_key_check=PASS
```

## 6. 恢复演练，不碰生产库

```bash
sudo -u medicalai python3 -m tools.medical_pilot.pilot_restore smoke \
  --backup /srv/medical/backups/pilot-YYYYMMDDTHHMMSSZ.sqlite
```

该命令在临时目录恢复为独立 SQLite、校验后删除，返回：

```text
production_database_replaced=false
temporary_candidate_removed=true
```

可在上线前和定期运维中反复执行。

## 7. 真正灾难恢复：先生成候选库

**不要直接把 backup 覆盖到 `/srv/medical/data/pilot.sqlite`。**

先停止所有会访问 SQLite 的真实服务：

```bash
sudo systemctl stop medical-agnes-worker.service
sudo systemctl stop medical-pilot.service
```

确认均非 active：

```bash
systemctl is-active medical-pilot.service
systemctl is-active medical-agnes-worker.service
```

然后生成独立候选：

```bash
cd /srv/medical/app
sudo -u medicalai python3 -m tools.medical_pilot.pilot_restore prepare \
  --backup /srv/medical/backups/pilot-YYYYMMDDTHHMMSSZ.sqlite \
  --output /srv/medical/data/pilot.restore-candidate.sqlite
```

要求：

```text
status=PASS
production_database_replaced=false
integrity_check=PASS
foreign_key_check=PASS
```

## 8. 人工原子切换前，保留旧 DB + WAL + SHM

只有候选库 PASS、API/Worker 已停止后，才允许管理员切换。

先生成 UTC 标记：

```bash
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
```

保留原生产三件套（存在才移动）：

```bash
sudo mv /srv/medical/data/pilot.sqlite /srv/medical/data/pilot.pre-restore-${STAMP}.sqlite
if [ -e /srv/medical/data/pilot.sqlite-wal ]; then
  sudo mv /srv/medical/data/pilot.sqlite-wal /srv/medical/data/pilot.pre-restore-${STAMP}.sqlite-wal
fi
if [ -e /srv/medical/data/pilot.sqlite-shm ]; then
  sudo mv /srv/medical/data/pilot.sqlite-shm /srv/medical/data/pilot.pre-restore-${STAMP}.sqlite-shm
fi
```

再提升已验证候选：

```bash
sudo mv /srv/medical/data/pilot.restore-candidate.sqlite /srv/medical/data/pilot.sqlite
sudo chown medicalai:medicalai /srv/medical/data/pilot.sqlite
sudo chmod 600 /srv/medical/data/pilot.sqlite
```

不要删除 `pilot.pre-restore-*`，直到恢复后的业务 smoke 全部 PASS。

## 9. 恢复后验证

先执行 host preflight：

```bash
cd /srv/medical/app
set -a
source /etc/medicalchannelai/pilot.env
set +a
sudo -E -u medicalai python3 -m tools.medical_pilot.pilot_host_preflight \
  --role all \
  --db /srv/medical/data/pilot.sqlite
```

再启动：

```bash
sudo systemctl start medical-pilot.service
sudo systemctl start medical-agnes-worker.service
```

至少验证：

```text
/api/healthz
登录 Session
/profile
/today
followup / reminders / followed
queue → Agnes worker → READY
outreach
```

全部通过前保留原 pre-restore 三件套。

## 10. 当前边界

- 备份允许在 API/Worker 在线时执行；SQLite Backup API 提供一致快照。
- 真正替换生产数据库必须停 API/Worker。
- 工具不会自动执行生产库替换。
- 每个备份都包含真实客户数据，必须按生产敏感数据保护。
- 当前只针对单机 SQLite Pilot；未来横向扩容改共享数据库后必须重新设计备份策略。
