# medicalai.qd.je Demo 快速上线

目标：只上线明确标注虚构数据的静态商务 Demo，不启动任何真实 Pilot API。

## 前置

- `medicalai.qd.je` DNS 可指向目标 VPS；
- VPS 80/443 可访问；
- VPS 已有 Git、Node/npm、Caddy；
- 推荐先用香港/日本/新加坡；现有美国 VPS 也可先试，但必须通过大陆/微信实测。

## 1. 代码

目标目录：

```text
/srv/medical/app
```

使用分支：

```text
dev/tianjin-pilot-v0.1
```

## 2. 构建

```bash
cd /srv/medical/app
bash deploy/build-web.sh demo
```

必须看到脚本完成，且没有：

- TypeScript error；
- build error；
- external runtime dependency error；
- 3 MiB Demo size budget error。

构建结果：

```text
/srv/medical/web
```

## 3. Caddy 只用静态 Demo 模板

```bash
sudo cp deploy/Caddyfile.demo.example /etc/caddy/Caddyfile
```

确保 Caddy 进程环境包含：

```text
MCAI_DOMAIN=medicalai.qd.je
```

然后：

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

**不要启动 `medical-pilot.service`。**

`medicalai.qd.je` Demo 的 `/api/*` 必须是404。

## 4. 自动 smoke

```bash
cd /srv/medical/app
MCAI_DOMAIN=medicalai.qd.je bash deploy/demo-smoke.sh
```

期望最后看到：

```text
PASS: static Demo smoke https://medicalai.qd.je
PASS: HTTPS / H5 shell / JS asset / SPA fallback / noindex / API isolation
```

## 5. 中国大陆 / 微信

再按：

```text
deploy/CHINA_ACCESS.md
```

实际测试。

必须：

- 微信直接点击；
- VPN关闭；
- 一条手机流量；
- 第二条运营商/宽带；
- 首页/TOP1/刷新/返回/话术/已联系/重置正常。

## 6. 发给老杨前

按：

```text
docs/product/demo.md
```

完整走一遍5分钟流程。

通过后再发送：

```text
https://medicalai.qd.je/
```

## 明确不做

本次 Demo 不做：

- 登录；
- 真实医院采购数据；
- 客户真实医院关系；
- Agnes API；
- `/api`；
- SQLite；
- discovery；
- Cloudflare；
- Vercel。

这些全部留在真实 Pilot 阶段。
