# MedicalChannelAI 部署

> `production_ready=false`。静态商务 Demo 与真实天津 Pilot 是两套不同安全级别的部署。

## 当前路线

### A. 给老杨看的静态商务 Demo

当前地址：

```text
https://medicalai.qd.je/
```

用户已实测中国大陆普通网络和微信内置浏览器可以打开。

Demo：

- 全部虚构数据；
- 无登录；
- 无 Session；
- 无真实 Agnes；
- 不启动 `pilot_server.py`；
- `/api/*` 直接 404；
- 只用于产品价值验证。

### B. 真实天津 Pilot

真实客户数据上线前使用**独立长期可控 HTTPS 域名**，H5 + `/api` 同源。

真实 Pilot 仍需82组 deterministic test modules 获得真实 PASS、Agnes smoke、Session/backup/discovery 验收。

## 目录

```text
/srv/medical/app       Git checkout
/srv/medical/web       H5 build output
/srv/medical/data      pilot.sqlite（真实 Pilot）
/srv/medical/backups   SQLite online backups（真实 Pilot）
/etc/medicalchannelai  server-only Pilot env
```

## 1. 系统用户与目录

```bash
sudo useradd --system --home /srv/medical --shell /usr/sbin/nologin medicalai || true
sudo mkdir -p /srv/medical/{app,web,data,backups} /etc/medicalchannelai
sudo chown -R medicalai:medicalai /srv/medical
sudo chmod 700 /srv/medical/data /srv/medical/backups /etc/medicalchannelai
```

把 `dev/tianjin-pilot-v0.1` checkout/copy 到 `/srv/medical/app`。

## 2. 构建静态 Demo

```bash
cd /srv/medical/app
sudo -u medicalai bash deploy/build-web.sh demo
```

脚本会真实执行：

- `npm ci`
- `npx tsc --noEmit`
- `npm run build`
- HTML/CSS 外部运行依赖扫描
- 默认3 MiB dist大小预算
- 发布到 `/srv/medical/web`

Demo 不要求 Python 后端 PASS。

## 3. Demo Caddy

静态 Demo **必须使用**：

```text
deploy/Caddyfile.demo.example
```

不要使用真实 Pilot 的 API 反代模板。

```bash
sudo cp deploy/Caddyfile.demo.example /etc/caddy/Caddyfile
```

Caddy 环境中的域名设为：

```text
MCAI_DOMAIN=medicalai.qd.je
```

然后：

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

Demo Caddy：

- `/api` 和 `/api/*` 固定404；
- `/assets/*` immutable一年缓存；
- SPA HTML `no-cache`；
- CSP/self-only；
- X-Robots-Tag noindex。

## 4. Demo 自动 smoke

DNS 和 HTTPS 生效后：

```bash
cd /srv/medical/app
MCAI_DOMAIN=medicalai.qd.je bash deploy/demo-smoke.sh
```

自动验证：

- HTTPS 首页；
- H5 root；
- 构建 JS asset；
- SPA `/today` 深链接；
- robots noindex；
- `/api/healthz` 必须404，证明静态 Demo 没有误接真实 API。

然后必须按 `deploy/CHINA_ACCESS.md` 做人工微信 + 两条独立大陆网络验收。

## 5. 大陆/微信验收

最重要的门槛：

```text
微信内置浏览器 + VPN关闭
```

至少另外再用：

- 一条国内手机流量；
- 另一运营商或家庭宽带。

首页、TOP1、刷新、返回、Demo话术、已联系、重置演示都正常后才发给老杨。

免费域名信誉可能变化，重要演示当天重新测试一次微信。

## 6. 真实 Pilot 构建

只有后端验证通过后：

```bash
cd /srv/medical/app
sudo -u medicalai bash deploy/build-web.sh pilot
```

此模式固定：

```text
VITE_BUILD_MODE=pilot
VITE_API_BASE_URL=/api
```

## 7. 真实 Pilot 域名与 canonical origin

真实 Pilot **不要默认继续使用 `medicalai.qd.je`**。

准备独立 HTTPS 域名，例如：

```text
https://<pilot-domain>
```

复制环境模板：

```bash
sudo cp deploy/pilot.env.example /etc/medicalchannelai/pilot.env
sudo chmod 600 /etc/medicalchannelai/pilot.env
sudo editor /etc/medicalchannelai/pilot.env
```

必须配置：

```text
MCAI_CANONICAL_ORIGIN=https://<pilot-domain>
MCAI_AGNES_API_KEY=...
```

后端安全策略：

- 未配置 `MCAI_CANONICAL_ORIGIN` → server拒绝启动；
- Host必须匹配 canonical authority；
- POST/PUT/PATCH/DELETE 的 Origin必须匹配 canonical origin；
- 不匹配统一403；
- loopback只允许 GET/HEAD `/api/healthz`。

## 8. 真实 Pilot Caddy

真实 Pilot 才使用：

```text
deploy/Caddyfile.example
```

它将 `/api/*` 反代到：

```text
127.0.0.1:8787
```

公网只暴露80/443，不直接暴露8787。

## 9. 真实 Pilot systemd

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

本地 health：

```bash
curl -fsS http://127.0.0.1:8787/api/healthz
```

loopback health 是唯一允许绕过 canonical Host 的 API 路径。

## 10. 真实 Pilot 最低验证

```bash
cd /srv/medical/app
python3 -m compileall -q tools/medical_pilot
python3 -m unittest discover -s tools/medical_pilot -t . -p "test_*.py" -v

cd web
npm ci
npx tsc --noEmit
VITE_BUILD_MODE=pilot VITE_API_BASE_URL=/api npm run build
```

必须获得真实 PASS；当前 GitHub Actions 没有分配 runner，因此仓库里的82个 tests 仍只是“已写入”。

## 11. 真实 Pilot public smoke

```bash
cd /srv/medical/app
bash deploy/pilot-smoke.sh https://<pilot-domain>
```

随后还必须做登录后的 Session/invite/follow-up/reminder/followed/outreach smoke。

## 12. Backup

```bash
python3 -m tools.medical_pilot.pilot_backup \
  --db /srv/medical/data/pilot.sqlite \
  --out-dir /srv/medical/backups \
  --keep 14
```

正式邀请真实用户前做至少一次 restore 演练。

## 禁止

- 禁止把 qd.je Demo 接真实客户 Session/画像；
- 禁止把 Mock Demo 介绍成真实医院采购数据；
- 禁止多个独立 SQLite 服务器同时对外；
- 禁止把 Agnes API Key 放进 `VITE_*`；
- 禁止浏览器提交 tenant/profile 作为可信身份；
- 禁止绕过 canonical Host/Origin；
- 禁止在真实 PASS 前合并 Draft PR #1 或设置 `production_ready=true`。
