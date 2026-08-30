# 天津 Pilot 单机部署

> `production_ready=false`。本目录只用于单机天津 Pilot，不允许复制成多 VPS / 多容器各自持有 SQLite。

## 推荐的两阶段上线

同一个域名先后切两种 H5 模式，不需要换地址：

### A. 给老杨先看：Demo

```text
https://medradar.dpdns.org/
```

H5 不配置 `VITE_API_BASE_URL`，明确显示“演示数据”，使用虚构 Mock 项目；不要求登录、不调用真实 Agnes、不冒充真实医院采购事实。

### B. 验证通过后：真实天津 Pilot

仍使用同一个地址，H5 重新以 `VITE_API_BASE_URL=/api` 构建，启用 invite/Session、真实后端数据、服务端 follow-up/reminder/outreach。

这样第一次商务演示不被后端验证进度卡住，同时后续不需要通知客户更换网址。

## 目标结构

```text
https://<pilot-domain>/
  -> Cloudflare（可选但推荐）
  -> Caddy
     -> /              /srv/medical/web (H5 dist)
     -> /api/*         127.0.0.1:8787

/srv/medical/app       Git checkout
/srv/medical/web       H5 build output
/srv/medical/data      pilot.sqlite
/srv/medical/backups   SQLite online backups
/etc/medicalchannelai  server-only Agnes env
/etc/caddy             Pilot domain env + Caddyfile
```

域名当前推荐：`medradar.dpdns.org` > `medicalai.dpdns.org` > `mcai.dpdns.org`。实际名称以注册时可用为准；正式收费版换独立域名。

## 1. 系统用户与目录

```bash
sudo useradd --system --home /srv/medical --shell /usr/sbin/nologin medicalai || true
sudo mkdir -p /srv/medical/{app,web,data,backups} /etc/medicalchannelai
sudo chown -R medicalai:medicalai /srv/medical
sudo chmod 700 /srv/medical/data /srv/medical/backups /etc/medicalchannelai
```

把 `dev/tianjin-pilot-v0.1` checkout/copy 到 `/srv/medical/app`，并确保代码目录由 `medicalai` 可读。

## 2. 构建 H5

统一使用 `deploy/build-web.sh`，它会先执行 `npm ci + tsc --noEmit` 再 build。

### Demo 模式

```bash
cd /srv/medical/app
sudo -u medicalai bash deploy/build-web.sh demo
```

### 真实 Pilot 模式

只有在 deterministic tests、H5 build 和真实后端 smoke 通过后再切：

```bash
cd /srv/medical/app
sudo -u medicalai bash deploy/build-web.sh pilot
```

客户浏览器不需要安装 Node/Python/命令行；Node 只属于服务器构建环境。

## 3. 服务端 Agnes Key

真实 Pilot 才需要：

```bash
sudo cp deploy/pilot.env.example /etc/medicalchannelai/pilot.env
sudo chmod 600 /etc/medicalchannelai/pilot.env
sudo editor /etc/medicalchannelai/pilot.env
```

真实 Key 禁止提交 GitHub、Issue、日志或 H5。

## 4. systemd：API / discovery / backup / healthcheck

真实 Pilot 安装：

```bash
sudo cp deploy/medical-pilot.service /etc/systemd/system/
sudo cp deploy/medical-discovery.service /etc/systemd/system/
sudo cp deploy/medical-discovery.timer /etc/systemd/system/
sudo cp deploy/medical-backup.service /etc/systemd/system/
sudo cp deploy/medical-backup.timer /etc/systemd/system/
sudo cp deploy/medical-healthcheck.service /etc/systemd/system/
sudo cp deploy/medical-healthcheck.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now medical-pilot.service
sudo systemctl enable --now medical-discovery.timer
sudo systemctl enable --now medical-backup.timer
sudo systemctl enable --now medical-healthcheck.timer
```

检查：

```bash
systemctl status medical-pilot.service
curl -fsS http://127.0.0.1:8787/api/healthz
```

`/api/healthz` 只用于 liveness，不返回 tenant/profile/Provider/model/API Key。真实业务 smoke 必须走登录后的 Session。

Discovery timer 每分钟触发一次**幂等调度 tick**，不代表每分钟对官网发请求；具体是否抓取由 readiness/cadence/持久化 slot 决定。

Backup timer 每天 `18:20 UTC = 02:20 Asia/Shanghai` 运行，使用 SQLite `Connection.backup()` + `PRAGMA integrity_check`，默认保留最近14份并输出 SHA-256。

## 5. Caddy + 域名

Caddy 只有一个域名变量：`MCAI_DOMAIN`。

```bash
sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo cp deploy/caddy-medical.env.example /etc/caddy/medicalchannelai.env
sudo chmod 600 /etc/caddy/medicalchannelai.env
sudo mkdir -p /etc/systemd/system/caddy.service.d
sudo cp deploy/caddy-medical.conf /etc/systemd/system/caddy.service.d/medicalchannelai.conf
sudo editor /etc/caddy/medicalchannelai.env
sudo systemctl daemon-reload
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

默认示例：

```text
MCAI_DOMAIN=medradar.dpdns.org
```

以后换正式域名主要改这一项；SQLite、客户画像、跟进、提醒和 AI 结果不需要迁移。

### Cloudflare 推荐顺序

1. DigitalPlat 把 `*.dpdns.org` 域名委派给外部 authoritative DNS；
2. 先使用 DNS-only，让域名直接指向 VPS；
3. Caddy 成功签发源站 HTTPS，浏览器直接访问确认正常；
4. 再按需要开启 Cloudflare proxy；
5. Cloudflare SSL/TLS 最终使用 `Full (strict)`；
6. `/api/auth/redeem` 做速率限制，`/api/*` 不缓存。

H5 和 API 必须同 origin；不要打开 permissive CORS。

## 6. 公开 smoke

Demo 模式：

```bash
curl -fsS https://<pilot-domain>/today >/dev/null
```

真实 Pilot：

```bash
cd /srv/medical/app
bash deploy/pilot-smoke.sh https://<pilot-domain>
```

该脚本验证：HTTPS healthz、H5 SPA、未登录 `/api/today` 必须保持401。它不替代 authenticated business smoke。

## 7. 首个真实 Pilot 账号

先写入客户 profile，再生成一次性邀请。邀请 URL 只发送给指定 Pilot 用户，不写公共日志。

```bash
cd /srv/medical/app
python3 -m tools.medical_pilot.pilot_admin \
  --db /srv/medical/data/pilot.sqlite \
  profile-put --file /path/to/profile.json

python3 -m tools.medical_pilot.pilot_admin \
  --db /srv/medical/data/pilot.sqlite \
  invite --tenant <tenant> --profile <profile> \
  --login-url https://<pilot-domain>
```

## 8. 真实 Pilot 上线前最低验收

```bash
cd /srv/medical/app
python3 -m compileall -q tools/medical_pilot
python3 -m unittest discover -s tools/medical_pilot -t . -p "test_*.py" -v

cd web
npm ci
npx tsc --noEmit
VITE_API_BASE_URL=/api npm run build
```

必须得到真实 PASS 后，才允许真实 Agnes smoke、Session/invite/follow-up/reminder/outreach smoke。

## 9. 手工备份验证

```bash
cd /srv/medical/app
python3 -m tools.medical_pilot.pilot_backup \
  --db /srv/medical/data/pilot.sqlite \
  --out-dir /srv/medical/backups \
  --keep 14
ls -lh /srv/medical/backups
```

正式邀请 Pilot 用户前还需要做一次 restore 验证。不要把活跃 SQLite 单文件 `cp` 当作唯一备份并忽略 WAL。

## 禁止

- 禁止把 Mock Demo 介绍成真实医院采购数据；
- 禁止把当前 SQLite runtime 复制到多个独立服务器同时对外；
- 禁止使用 Serverless 临时本地文件系统保存 Pilot 数据；
- 禁止把 Agnes API Key 放进 `VITE_*`；
- 禁止让浏览器提交 tenant/profile 作为可信身份；
- 禁止在真实 PASS 前把 Draft PR #1 合并或标记 `production_ready=true`。
