# Tianjin Pilot Host Acceptance

Status: `REQUIRED_BEFORE_REAL_PILOT_START_2026-08-31`

本验收用于真实单机 Pilot 主机。它必须在创建老杨账号、写入真实客户资料、启动常驻 Agnes Worker 之前执行。

## 1. 固定目录与身份

```text
应用目录：/srv/medical/app
持久数据：/srv/medical/data/pilot.sqlite
服务用户：medicalai
环境文件：/etc/medicalchannelai/pilot.env
```

当前 SQLite 方案只允许单机或同一主机多进程。禁止把同一个 Pilot 复制成多台独立 SQLite 实例后同时服务客户。

## 2. 安装三个 systemd unit

```bash
cd /srv/medical/app
sudo cp deploy/medical-pilot.service /etc/systemd/system/
sudo cp deploy/medical-agnes-worker.service /etc/systemd/system/
sudo cp deploy/medical-pilot-acceptance.service /etc/systemd/system/
sudo systemctl daemon-reload
```

`medical-pilot-acceptance.service` 是手工 oneshot gate，不可 enable 为常驻服务。

API 和 Worker unit 都要求真实存在：

```text
/etc/medicalchannelai/pilot.env
```

并在 `ExecStartPre` 中执行 `pilot_host_preflight`。环境文件缺失、canonical origin 错误、Agnes Key 缺失（Worker）、Agnes endpoint 越界、数据库目录不可写时，服务必须 fail-closed。

## 3. 创建 root 控制的环境文件

```bash
sudo install -d -m 700 /etc/medicalchannelai
sudo editor /etc/medicalchannelai/pilot.env
sudo chown root:root /etc/medicalchannelai/pilot.env
sudo chmod 600 /etc/medicalchannelai/pilot.env
```

内容：

```text
MCAI_CANONICAL_ORIGIN=https://<真实Pilot独立域名>
MCAI_AGNES_API_KEY=<server-only-key>
# 通常不要设置；确需设置时只能使用代码 allowlist 内官方 /v1 endpoint。
# MCAI_AGNES_BASE_URL=https://apihub.agnes-ai.com/v1
```

禁止把 Key 放入 GitHub、命令行参数、URL、浏览器、SQLite 客户画像或日志。

## 4. 准备数据目录

```bash
sudo install -d -o medicalai -g medicalai -m 700 /srv/medical/data
```

统一 acceptance 只检查 `/srv/medical/data/pilot.sqlite` 的路径/权限；**不会写这个生产数据库**。

## 5. 一条命令执行完整主机验收

```bash
sudo systemctl start medical-pilot-acceptance.service
```

查看结果：

```bash
sudo systemctl status medical-pilot-acceptance.service --no-pager
sudo journalctl -u medical-pilot-acceptance.service -n 50 --no-pager
```

验收入口：

```text
tools.medical_pilot.pilot_host_acceptance
deploy/pilot-host-acceptance-v0.1.json
```

它按以下顺序 fail-closed：

1. `pilot_host_preflight --role all`：检查真实 Pilot DB 路径权限、canonical origin、Agnes Key、Agnes 官方 endpoint；
2. 在**临时 SQLite** 中访问5条冻结的官方采购 URL，要求 `5 success / 0 failure`；
3. 下载冻结的天津财政官方 `XCSD-2026-C-181项目需求书.docx`，要求真实 HTTP bytes、MIME/size/SHA-256、OOXML parser block；
4. 在**临时 SQLite lease store** 中用合成 grounded input 发起真实 Agnes authenticated contract smoke，仍经过正式 global lease 和 `validate_model_decision`；
5. 四个阶段全部 PASS 才返回 overall `status=PASS`。

输出为安全 JSON，不输出 API Key、provider response body、完整 model input、附件正文或客户资料。

示意：

```json
{
  "status": "PASS",
  "production_data_touched": false,
  "host_preflight": {"status": "PASS"},
  "official_bootstrap": {"status": "PASS", "success_count": 5, "failure_count": 0},
  "attachment": {"status": "PASS", "size_bytes": 12345, "sha256": "..."},
  "agnes_provider": {"status": "PASS", "contract_validation_passed": true}
}
```

没有看到 overall `PASS` 就不得启用真实 Pilot。

## 6. Acceptance PASS 后才写真实生产库

Acceptance 中的5条 bootstrap 使用临时 SQLite，不会把它们写入 `/srv/medical/data/pilot.sqlite`。

PASS 后执行正式首次导入：

```bash
cd /srv/medical/app
sudo -u medicalai python3 -m tools.medical_pilot.pilot_live_seed \
  --db /srv/medical/data/pilot.sqlite \
  --manifest deploy/tianjin-pilot-bootstrap-urls-2026-08-30.json
```

要求：

```text
success_count=5
failure_count=0
```

项目编号在持久化前与 manifest expected code 核对；不写客户关系，不写预制 Agnes 结论。

## 7. 再启动 API 与 Worker

```bash
sudo systemctl enable --now medical-pilot.service
sudo systemctl enable --now medical-agnes-worker.service
sudo systemctl status medical-pilot.service --no-pager
sudo systemctl status medical-agnes-worker.service --no-pager
```

本机 health：

```bash
curl --fail --silent --show-error http://127.0.0.1:8787/api/healthz
```

随后再通过 canonical HTTPS 域名验证浏览器登录/profile/Today Actions。

## 8. 老杨账号是后续步骤，不是主机测试工具

只有完成：

```text
Host Acceptance PASS
→ 生产库5/5 bootstrap
→ API / Worker 正常
→ queue → real Agnes → READY smoke
```

之后才创建老杨 `INVITED` 账号并发送一次性注册链接。

第一次真实 provider 调用、第一次附件验证、第一次服务器配置错误排查都不能拿老杨账号试。

## 9. 当前仍不能宣称

在目标主机真实运行本验收并得到 PASS 之前，继续保持：

```text
production_ready=false
real_authenticated_agnes_provider_pass=false
real_attachment_binary_capture_count=0
PR #1 = Draft / do not merge
```
