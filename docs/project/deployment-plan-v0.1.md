# MedicalChannelAI 天津 Pilot 部署方案 v0.1

状态：`FROZEN_FOR_SINGLE_HOST_PILOT`  
日期：2026-08-30  
生产就绪：`false`

## 当前决策

### 商务 Demo

给老杨看的静态商务 Demo 当前使用：

```text
https://medicalai.qd.je/
```

原因：用户已经在真实目标环境验证：

- 中国大陆普通网络可访问；
- 微信内置浏览器可直接点击打开。

当前 `medradar.dpdns.org` 在微信实测中打不开，因此不再作为商务 Demo 首选。

### 真实 Pilot / 正式版

`qd.je` 当前存在 Public Suffix List / Cloudflare zone 兼容问题，因此它只承担**无登录、无真实客户数据的静态 Demo**。

真实 Pilot 开始启用 Session、客户画像、follow-up、提醒和模型结果前，优先换独立长期可控域名。

不再强求免费 Demo 域名与正式 Pilot 永久同域。

## 为什么 qd.je 现在适合 Demo

Demo 当前：

- 无登录；
- 无 Session Cookie；
- 无真实客户画像；
- 无真实采购数据；
- 无真实 Agnes Key；
- 全部项目/联系人/金额均为明确标注的虚构演示数据。

因此 qd.je 当前 PSL 状态不会影响 Demo 的客户数据隔离。

## 中国大陆 / 微信访问是硬门槛

目标不是“国外能打开”，而是：

> 老杨在天津、关闭 VPN，用微信直接点击链接可以打开并完成完整演示路径。

验收见：`deploy/CHINA_ACCESS.md`。

发链接前必须：

1. 微信内置浏览器可打开；
2. 至少2条独立大陆网络可访问；
3. 全程关闭 VPN/Clash/WARP；
4. HTTPS无证书警告；
5. 首页/TOP1/刷新/返回/话术/重置正常。

免费域名信誉会变化，因此每次重要演示当天都要重新用微信点一次。

## Demo 网络拓扑

当前推荐：

```text
medicalai.qd.je
  ↓ DNS
境外源站
  ↓ HTTPS
Caddy
  ↓
静态 H5
```

`qd.je` 当前不能稳定作为普通 Cloudflare zone 接入，所以 Demo 不依赖 Cloudflare。

源站优先：

1. 香港
2. 日本
3. 新加坡
4. 美国西海岸
5. 现有美国 Google VPS 仅作为零新增成本测试

如果美国源站在微信/天津网络慢，不换产品代码，只把 DNS 切到香港/日本/新加坡新源站。

## H5 大陆访问约束

商务 Demo 首屏不得依赖：

- Google Fonts
- jsDelivr / unpkg / cdnjs
- Google APIs
- `*.vercel.app`
- `*.pages.dev`
- `*.workers.dev`
- 外部图片/字体/脚本作为首屏必需资源

`deploy/build-web.sh demo` 会真实执行：

```text
npm ci
npx tsc --noEmit
npm run build
```

并额外执行：

- HTML/CSS 外部运行依赖扫描；
- Demo dist 总大小预算（默认3 MiB）；
- 发布到 `/srv/medical/web`。

Caddy 对 Vite hash assets 使用长缓存；SPA HTML使用 `no-cache`，兼顾跨境访问和快速更新。

## Demo 产品边界

```text
VITE_BUILD_MODE=demo
VITE_API_BASE_URL=
```

要求：

- 虚构医院、项目、联系人、金额、客户画像；
- 明确显示“演示数据”；
- 不登录；
- 不调用真实 Agnes；
- 不冒充真实采购事实；
- 不允许搜索引擎收录；
- 公开依据不足时不能生成沟通话术。

## 真实天津 Pilot

后端验证完成后，使用独立正式/试点域名：

```text
https://<pilot-domain>/
https://<pilot-domain>/api/*
```

构建：

```text
VITE_BUILD_MODE=pilot
VITE_API_BASE_URL=/api
```

然后才启用：

- invite / opaque Session
- 真实客户画像
- 真实采购事实
- server follow-up
- reminder
- `/followed`
- grounded outreach

真实 Pilot H5 + API 必须同源。

## 单机 Pilot 拓扑

```text
浏览器
  ↓ HTTPS
独立 Pilot 域名
  ↓
Caddy
  ├─ /      → /srv/medical/web
  └─ /api/* → 127.0.0.1:8787
                    ↓
             pilot_server.py
                    ↓
             /srv/medical/data/pilot.sqlite
```

公网只开放80/443；不直接暴露8787。

SQLite runtime 当前只允许一台长期在线服务器；禁止多个 VPS / 容器各自持有独立 SQLite 同时对外。

## 仓库部署文件

- `deploy/README.md`
- `deploy/README_DOMAIN.md`
- `deploy/CHINA_ACCESS.md`
- `deploy/Caddyfile.example`
- `deploy/build-web.sh`
- `deploy/pilot-smoke.sh`
- API/discovery/backup/healthcheck systemd service/timer
- `tools/medical_pilot/pilot_backup.py`

这些部署脚手架尚未在真实目标服务器完成执行验证。

## Demo 上线门槛

Demo 不需要等待81组 Python 后端测试，但必须完成：

1. 目标服务器 `npm ci` PASS；
2. TypeScript PASS；
3. Demo build PASS；
4. 外部运行依赖扫描 PASS；
5. dist大小预算 PASS；
6. HTTPS PASS；
7. 微信内置浏览器 PASS；
8. 两条独立大陆网络无VPN PASS；
9. `docs/product/demo.md` 商务演示走查 PASS。

## 真实 Pilot 上线门槛

至少需要：

1. 81组 deterministic tests 真实 PASS；
2. Demo/Pilot 两种 H5 build 真实 PASS；
3. server-only Agnes grounded outreach smoke；
4. HTTPS + Session/invite/follow-up/reminder/followed/outreach smoke；
5. SQLite backup + restore 演练；
6. 真实 discovery tick 与 latency 记录。

PR #1 在这些真实 Pilot 验证完成前保持 Draft，`production_ready=false`。
