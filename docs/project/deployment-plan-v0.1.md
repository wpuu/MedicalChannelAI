# MedicalChannelAI 天津 Pilot 部署方案 v0.1

状态：`FROZEN_FOR_SINGLE_HOST_PILOT`  
日期：2026-08-30  
生产就绪：`false`

## 结论

天津 Pilot 首版采用：

```text
浏览器
  ↓ HTTPS
Pilot 域名
  ↓
Cloudflare DNS / Proxy（可选但推荐）
  ↓ HTTPS
单台长期在线 VPS
  ├─ Caddy/Nginx：TLS、静态 H5、反向代理
  ├─ /            → web/dist
  ├─ /api/*       → 127.0.0.1:8787
  ├─ pilot_server.py
  ├─ discovery scheduler
  └─ /srv/medical/pilot.sqlite
```

H5 与 API 必须保持同一 canonical origin，继续使用：

```text
VITE_API_BASE_URL=/api
```

这样可保留现有：

- `__Host-mcai_session`
- `Secure`
- `HttpOnly`
- `SameSite=Strict`
- same-origin API
- 单机 SQLite 原子状态

## 域名策略

### 天津 Pilot

允许使用免费域名作为临时入口，例如：

```text
medicalchannelai.dpdns.org
```

这里只是命名示例，实际名称必须以注册时可用性为准。

`dpdns.org` 只承担域名注册/委派角色，不承担 MedicalChannelAI 后端计算或 SQLite 持久化。

推荐把该域名委派给 Cloudflare，再由 Cloudflare DNS 指向 Pilot VPS。

### 正式商业版

正式对医院渠道客户、经销商、厂家销售收费前，应迁移到独立、长期可控的付费域名，例如：

```text
<brand>.com
<brand>.cn
<brand>.ai
```

具体品牌和域名后续单独确定。

免费域名适合作为 Pilot/内部测试入口，不作为长期品牌资产依赖。

## TLS / Cloudflare

如启用 Cloudflare Proxy：

- 浏览器到 Cloudflare 必须 HTTPS；
- Cloudflare 到源站也必须 HTTPS；
- 目标模式为 `Full (strict)`；
- 源站证书可使用有效公共 CA 证书或 Cloudflare Origin CA；
- 不采用仅浏览器侧加密、源站明文的 Flexible 模式作为 Pilot 正式配置。

## 单机目录建议

```text
/srv/medical/
  app/                 # MedicalChannelAI checkout / release
  web/                 # web/dist 构建产物
  pilot.sqlite         # 单机 Pilot 持久数据
  backups/             # SQLite 备份
  logs/                # 服务日志（禁止写 Key/session/invite 原文）
```

服务端 Secret 只放操作系统环境或受限 Secret 文件：

```text
MCAI_AGNES_API_KEY=...
MCAI_AGNES_BASE_URL=...   # 可选，仍受代码 allowlist
```

禁止写入：

- GitHub
- H5 bundle
- SQLite 业务表
- URL/query
- 客户可见日志

## 进程

Pilot 至少需要两个长期任务：

1. API server

```text
python -m tools.medical_pilot.pilot_server \
  --db /srv/medical/pilot.sqlite \
  --host 127.0.0.1 \
  --port 8787
```

2. Discovery tick

```text
python -m tools.medical_pilot.discovery_scheduler \
  --db /srv/medical/pilot.sqlite
```

Discovery 仍按现有策略每分钟触发一次幂等 tick；只有 `DISCOVERY_READY` Source 真正执行。

正式部署时使用 systemd 或等价进程管理，不用人工终端长期挂着。

## H5 发布

```text
cd web
npm ci
VITE_API_BASE_URL=/api npm run build
```

只发布 `web/dist`。

Vite/Node 仅用于服务器或 CI 构建，不要求客户电脑安装 Node。

## 当前禁止

首版不部署成：

- 多 VPS 各自一份 SQLite；
- 多容器各自一份 SQLite；
- Vercel/Cloudflare Function 本地文件系统保存 `pilot.sqlite`；
- H5 在一个域名、API 在另一个跨域地址，再让浏览器自行传 tenant/profile；
- 直接把 `127.0.0.1:8787` 暴露公网。

## 从免费 Pilot 域名迁移正式域名

业务数据和身份不绑定 `dpdns.org` 名称。

迁移步骤应为：

1. 新正式域名接入 Cloudflare；
2. 新域名指向同一 VPS；
3. 源站证书覆盖新域名；
4. H5 仍保持 `VITE_API_BASE_URL=/api`；
5. 邀请链接改为新域名；
6. 旧 Pilot 域名停止发放新 invite；
7. 短期只做 301/停用提示，不跨域搬运 Session Cookie；
8. 用户在正式域名重新登录/兑换邀请。

SQLite 中的公开事实、客户画像、follow-up、reminder 和 outreach cache 不需要因为域名变化而重建。

## 上线前硬门槛

当前还不能标记已上线。至少需要：

1. Python deterministic tests 获得真实执行 PASS；
2. TypeScript typecheck + H5 build 获得真实 PASS；
3. server-only Agnes outreach smoke；
4. 单机 VPS 上 Session/invite/follow-up/reminder/outreach 实测；
5. HTTPS + `Full (strict)` 验证；
6. SQLite 备份/恢复演练；
7. 首批真实 Pilot profile 与数据源运行验证。
