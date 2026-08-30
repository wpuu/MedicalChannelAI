# MedicalChannelAI 天津 Pilot 部署方案 v0.1

状态：`FROZEN_FOR_SINGLE_HOST_PILOT`  
日期：2026-08-30  
生产就绪：`false`

## 结论

天津 Pilot 采用单域名单机架构：

```text
浏览器
  ↓ HTTPS
Pilot 域名
  ↓
Cloudflare DNS / Proxy（可选但推荐）
  ↓ HTTPS
Caddy
  ├─ /            → /srv/medical/web
  └─ /api/*       → 127.0.0.1:8787
                         ↓
                  pilot_server.py
                         ↓
                  /srv/medical/data/pilot.sqlite
```

运行与备份：

```text
/srv/medical/app       Git checkout / release
/srv/medical/web       H5 build output
/srv/medical/data      pilot.sqlite
/srv/medical/backups   consistent SQLite backups
```

当前 SQLite runtime 只允许一台长期在线服务器；禁止多个 VPS / 容器分别持有独立 SQLite 后同时对外。

## 给老杨演示：同一域名两阶段

为了不让第一次商务演示被真实后端验证进度阻塞，同时不换网址：

### 阶段 A：Demo

首选地址：

```text
https://medradar.qzz.io/
```

备用：

```text
https://medradar.dpdns.org/
```

构建：

```text
VITE_BUILD_MODE=demo
VITE_API_BASE_URL=
```

要求：

- 页面明确显示“演示数据”；
- 只使用虚构 Mock 医疗项目；
- 不要求登录；
- 不调用真实 Agnes；
- 不把 Mock 描述成真实医院采购事实。

### 阶段 B：真实天津 Pilot

验证完成后仍使用同一个域名，重新构建：

```text
VITE_BUILD_MODE=pilot
VITE_API_BASE_URL=/api
```

然后启用：invite / Session / 真实后端 / 服务端 follow-up / reminder / followed / grounded outreach。

前端已增加 build-mode fail-closed：Demo 不允许同时配置真实 API；Pilot 必须使用 `/api`。

## 域名策略

DigitalPlat Domains 当前提供包括：

- `*.qzz.io`
- `*.dpdns.org`

并支持外部 nameserver/DNS provider。

当前业务演示推荐顺序：

1. `medradar.qzz.io`
2. `medicalai.qzz.io`
3. `medradar.dpdns.org`
4. `mcai.dpdns.org`

实际名称是否可用以注册平台实时结果为准。

`qzz.io` 更短，更适合非技术客户看到的网址；免费 namespace 仍不作为正式商业品牌资产或企业邮箱主域长期依赖。

正式收费后换独立长期可控域名，例如 `<brand>.com/.cn/.ai`。域名切换不需要迁移 SQLite 中的采购事实、客户画像、follow-up、reminder 或 outreach cache。

## DNS / TLS / Cloudflare

推荐首次上线顺序：

1. 注册选定的 `qzz.io` / `dpdns.org` 名称；
2. 委派给外部 authoritative DNS；
3. DNS A/AAAA 指向单台 VPS；
4. 若使用 Cloudflare，首次先 DNS-only；
5. Caddy 直接完成源站 HTTPS 证书签发；
6. 浏览器直连确认 HTTPS 正常；
7. 再按需开启 Cloudflare proxy；
8. Cloudflare TLS 使用 `Full (strict)`；
9. `/api/auth/redeem` 做速率限制；
10. `/api/*` 不缓存。

不采用 Flexible 模式作为真实 Pilot 配置。

## Same-origin 身份边界

真实 Pilot 的 H5 和 API 必须保持同一 canonical origin：

```text
https://<pilot-domain>/
https://<pilot-domain>/api/*
```

这样保留现有：

- `__Host-mcai_session`
- `Secure`
- `HttpOnly`
- `SameSite=Strict`
- trusted Session tenant/profile
- no permissive CORS

浏览器不得自报 tenant/profile 作为可信身份。

## 仓库部署文件

运维命令以 `deploy/README.md` 为准。

当前已经写入：

- `deploy/Caddyfile.example`
- `deploy/caddy-medical.env.example`
- `deploy/caddy-medical.conf`
- `deploy/build-web.sh`
- `deploy/pilot-smoke.sh`
- `deploy/medical-pilot.service`
- `deploy/medical-discovery.service` + `.timer`
- `deploy/medical-backup.service` + `.timer`
- `deploy/medical-healthcheck.service` + `.timer`
- `deploy/pilot.env.example`

这些是部署脚手架，**尚未在真实 VPS 执行**。

## API server

```text
python3 -m tools.medical_pilot.pilot_server \
  --db /srv/medical/data/pilot.sqlite \
  --host 127.0.0.1 \
  --port 8787
```

公网只暴露 Caddy 80/443；不得直接暴露 8787。

## Discovery

systemd timer 每分钟调用一个幂等 tick：

```text
python3 -m tools.medical_pilot.discovery_scheduler \
  --db /srv/medical/data/pilot.sqlite
```

这不表示每分钟抓官网；readiness、cadence、source backoff 和持久化 slot 决定是否真正请求。

当前只有 2/7 Source 自动 listing discovery ready，其余5个仍 fail-closed。

## Health

公开 liveness：

```text
GET /api/healthz
```

固定返回非敏感 Public View，仅说明单机 Pilot 进程存活。不得包含 tenant/profile、业务数据、Provider、模型名或 API Key。

它不代替登录后的业务 smoke。

## Backup

`tools/medical_pilot/pilot_backup.py` 使用 SQLite `Connection.backup()` 进行在线一致性备份，并执行：

```text
PRAGMA integrity_check
SHA-256
```

默认 systemd timer：北京时间每日 02:20；默认保留14份。

正式邀请真实 Pilot 用户前必须做至少一次 backup + restore 实测。

## Secret

服务器 Secret：

```text
MCAI_AGNES_API_KEY=...
MCAI_AGNES_BASE_URL=...   # 可选，仍受代码 allowlist
```

禁止进入：GitHub、H5 bundle、SQLite 业务表、URL/query、客户日志。

## 当前禁止

- 多 VPS 各自一份 SQLite；
- 多容器各自一份 SQLite；
- Vercel/Serverless 临时本地文件系统保存 `pilot.sqlite`；
- H5/API 跨域后让浏览器自报身份；
- 直接把 127.0.0.1:8787 暴露公网；
- 把 Demo Mock 介绍成真实采购数据；
- 在真实执行 PASS 前把 PR #1 合并或标记 production_ready=true。

## 从免费演示域名迁移正式域名

1. 正式域名指向同一 VPS；
2. 配置新 TLS；
3. `MCAI_DOMAIN` 改成新域名；
4. H5 真实 Pilot 仍使用 `/api`；
5. 新 invite 改为新域名；
6. 旧免费域名停止发新 invite；
7. 不跨域搬运 Session Cookie，用户在新域名重新登录；
8. SQLite 业务数据无需重建。

## 上线前硬门槛

真实天津 Pilot 至少需要：

1. 81 组 deterministic tests 获得真实执行 PASS；
2. Demo/Pilot 两种 H5 TypeScript/build 均真实 PASS；
3. server-only Agnes grounded outreach smoke；
4. 单机 VPS HTTPS + Session/invite/follow-up/reminder/followed/outreach smoke；
5. `/api/healthz` + public HTTPS smoke；
6. SQLite backup + restore 演练；
7. 真实 discovery tick 与 latency 记录。

Demo 给老杨预览可以早于真实 Pilot 后端上线，但必须始终明确标识“演示数据”。
