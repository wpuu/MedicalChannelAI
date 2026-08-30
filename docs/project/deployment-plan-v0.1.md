# MedicalChannelAI 天津 Pilot 部署方案 v0.1

状态：`FROZEN_FOR_SINGLE_HOST_PILOT`  
日期：2026-08-30  
生产就绪：`false`

## 结论

当前不再考虑收费的 `qzz.io` 作为测试入口。

给老杨看的免费商务 Demo：

1. **首选：`medradar.dpdns.org`**
2. 应急验证：现有 `wpu.dpdns.org` 只用于证明 dpdns 链路可工作，不改动它当前业务
3. `medicalai.qd.je` 只做备选，不作为首选：`qd.je` 当前存在 Public Suffix / Cloudflare zone 兼容问题

正式商业化后再换独立长期可控域名。

## 中国大陆访问是硬门槛

目标不是“国外能打开”，而是：

> 老杨在天津使用普通手机流量或家庭宽带、不开 VPN，可以直接打开。

Cloudflare 官方明确说明，普通全球网络跨中国网络边界时可能出现明显延迟和可靠性问题；真正的 Cloudflare China Network 是单独的 Enterprise 服务并要求 ICP。

因此免费 Demo 默认采用：

```text
medradar.dpdns.org
  ↓ DNS-only
境外源站
  ↓ HTTPS
Caddy
  ↓
静态 H5
```

**第一轮大陆验收不依赖 Cloudflare 橙云代理。**

完整验收见：`deploy/CHINA_ACCESS.md`。

## 源站选择

为了大陆访问，服务器优先级：

1. 香港
2. 东京 / 大阪
3. 新加坡
4. 美国西海岸
5. 现有美国 Google VPS 作为零新增成本试验

如果美国 VPS 在天津网络慢，不改域名、不改前端，直接把 DNS 指向香港/日本/新加坡的新源站即可。

## H5 国内访问约束

商务 Demo 首屏不得依赖国外第三方运行资源：

- Google Fonts
- jsDelivr / unpkg / cdnjs
- Google APIs
- `*.vercel.app`
- `*.pages.dev`
- `*.workers.dev`
- 外部脚本/字体/样式作为首屏必需资源

`deploy/build-web.sh demo` 在构建后会扫描产物；发现外部 `script/link/@import` 运行依赖则直接失败。

## 给老杨演示：同一域名两阶段

### 阶段 A：商务 Demo

```text
https://medradar.dpdns.org/
```

构建：

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

### 阶段 B：真实天津 Pilot

后端验证完成后仍使用同一个域名：

```text
VITE_BUILD_MODE=pilot
VITE_API_BASE_URL=/api
```

然后启用真实 invite / Session / 客户画像 / 采购事实 / follow-up / reminder / followed / grounded outreach。

前端 build-mode fail-closed，防止 Demo/Pilot 串模式。

## 单机 Pilot 拓扑

```text
浏览器
  ↓ HTTPS
medradar.dpdns.org
  ↓ DNS
Caddy
  ├─ /      → /srv/medical/web
  └─ /api/* → 127.0.0.1:8787
                    ↓
             pilot_server.py
                    ↓
             /srv/medical/data/pilot.sqlite
```

公网只开放 80/443，不直接暴露 8787。

SQLite runtime 当前只允许一台长期在线服务器；禁止多个 VPS / 容器各自持有独立 SQLite 同时对外。

## DNS / TLS

Demo 第一轮：

1. 注册 `medradar.dpdns.org`；
2. DNS A/AAAA 直接指向源站；
3. Caddy 获取 HTTPS 证书；
4. 用天津/大陆普通网络验收；
5. 通过后再把链接发给老杨。

Cloudflare proxy 是后续可选实验，不是前置条件。若开启后国内访问变慢或不稳定，退回 DNS-only。

真实商业化若需要大陆 CDN/节点，再独立评估 ICP、国内云/CDN 或 Cloudflare China Network。

## Same-origin 身份边界

真实 Pilot 保持：

```text
https://medradar.dpdns.org/
https://medradar.dpdns.org/api/*
```

保留：

- `__Host-mcai_session`
- Secure
- HttpOnly
- SameSite=Strict
- trusted Session tenant/profile
- 无宽泛 CORS

浏览器不得自报 tenant/profile 作为可信身份。

## 仓库部署文件

- `deploy/README.md`
- `deploy/README_DOMAIN.md`
- `deploy/CHINA_ACCESS.md`
- `deploy/Caddyfile.example`
- `deploy/build-web.sh`
- `deploy/pilot-smoke.sh`
- API/discovery/backup/healthcheck systemd service/timer
- `tools/medical_pilot/pilot_backup.py`

当前都是**已写部署脚手架，尚未在真实目标服务器执行**。

## Demo 上线门槛

Demo 不需要等待81组 Python 后端测试，但必须在实际部署环境完成：

1. `npm ci`
2. `npx tsc --noEmit`
3. `npm run build`
4. 外部运行资源扫描 PASS
5. HTTPS 无证书错误
6. 两条独立大陆网络、无 VPN 验收 PASS
7. 按 `docs/product/demo.md` 完成商务演示走查

## 真实 Pilot 上线门槛

真实天津 Pilot 仍至少需要：

1. 81组 deterministic tests 真实 PASS；
2. Demo/Pilot 两种 H5 build 真实 PASS；
3. server-only Agnes grounded outreach smoke；
4. HTTPS + Session/invite/follow-up/reminder/followed/outreach smoke；
5. SQLite backup + restore 演练；
6. 真实 discovery tick 与 latency 记录。

PR #1 在这些验证完成前保持 Draft，`production_ready=false`。