# 天津 Pilot 单机部署

> `production_ready=false`。本目录只用于单机天津 Pilot，不允许复制成多 VPS / 多容器各自持有 SQLite。

## 目标结构

```text
https://<pilot-domain>/
  -> Caddy
     -> /              /srv/medical/web (H5 dist)
     -> /api/*         127.0.0.1:8787

/srv/medical/app       Git checkout
/srv/medical/web       H5 build output
/srv/medical/data      pilot.sqlite
/etc/medicalchannelai  server-only env
```

## 1. 系统用户与目录

```bash
sudo useradd --system --home /srv/medical --shell /usr/sbin/nologin medicalai || true
sudo mkdir -p /srv/medical/{app,web,data} /etc/medicalchannelai
sudo chown -R medicalai:medicalai /srv/medical
sudo chmod 700 /srv/medical/data /etc/medicalchannelai
```

## 2. 部署代码与构建 H5

把 `dev/tianjin-pilot-v0.1` checkout 到 `/srv/medical/app`，然后在服务器构建：

```bash
cd /srv/medical/app/web
npm ci
VITE_API_BASE_URL=/api npm run build
sudo rsync -a --delete dist/ /srv/medical/web/
sudo chown -R medicalai:medicalai /srv/medical/web
```

Node 只存在于服务器构建环境；客户浏览器不需要安装 Node/Python/命令行。

## 3. 服务端 Agnes Key

```bash
sudo cp deploy/pilot.env.example /etc/medicalchannelai/pilot.env
sudo chmod 600 /etc/medicalchannelai/pilot.env
sudo editor /etc/medicalchannelai/pilot.env
```

只填写服务器环境变量。真实 Key 禁止提交 GitHub、Issue、日志或 H5。

## 4. systemd

```bash
sudo cp deploy/medical-pilot.service /etc/systemd/system/
sudo cp deploy/medical-discovery.service /etc/systemd/system/
sudo cp deploy/medical-discovery.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now medical-pilot.service
sudo systemctl enable --now medical-discovery.timer
```

检查：

```bash
systemctl status medical-pilot.service
systemctl status medical-discovery.timer
curl -i http://127.0.0.1:8787/api/today
```

未认证的 `/api/today` 返回 401 属于正常现象；不应为了健康检查关闭认证。

## 5. Caddy + 域名

`deploy/Caddyfile.example` 使用：

- `MCAI_DOMAIN`：例如 `mcai.dpdns.org`
- `ACME_EMAIL`：证书通知邮箱

安装到 Caddy 配置后：

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

H5 与 API 必须保持同 origin。不要额外开启 permissive CORS。

若前置使用 Cloudflare：

- DNS 指向本 VPS；
- 等待 DNS / Universal SSL 生效；
- SSL/TLS 使用 `Full (strict)`；
- `/api/auth/redeem` 在边缘或反代层增加速率限制；
- 不缓存 `/api/*`。

## 6. 首个 Pilot 账号

先写入客户 profile，再生成一次性邀请。邀请 URL 只发送给指定 Pilot 用户，不写入公共日志。

```bash
python3 -m tools.medical_pilot.pilot_admin \
  --db /srv/medical/data/pilot.sqlite \
  profile-put --file /path/to/profile.json

python3 -m tools.medical_pilot.pilot_admin \
  --db /srv/medical/data/pilot.sqlite \
  invite --tenant <tenant> --profile <profile> \
  --login-url https://<pilot-domain>
```

## 7. 上线前最低验收

当前 GitHub-hosted runner 仍未实际执行测试，因此在真正给 Pilot 用户前必须在可信执行环境完成：

```bash
cd /srv/medical/app
python3 -m compileall -q tools/medical_pilot
python3 -m unittest discover -s tools/medical_pilot -t . -p "test_*.py" -v

cd web
npm ci
npx tsc --noEmit
VITE_API_BASE_URL=/api npm run build
```

全部真实 PASS 后，才允许继续真实 Agnes smoke、Session/invite/follow-up/reminder/outreach smoke。

## 8. 备份

Pilot SQLite 属于业务数据，至少每日备份。备份前优先使用 SQLite backup API 或停写窗口；不要在数据库持续写入时直接复制一个可能不一致的单独 `.sqlite` 文件并忽略 WAL。

## 禁止

- 禁止把当前 SQLite runtime 复制到多个独立服务器后同时对外；
- 禁止使用 Vercel/Serverless 临时本地文件系统保存 Pilot 数据；
- 禁止把 Agnes API Key 放进 `VITE_*`；
- 禁止让浏览器提交 tenant/profile 作为可信身份；
- 禁止在真实 PASS 前把 Draft PR #1 合并或标记 `production_ready=true`。
