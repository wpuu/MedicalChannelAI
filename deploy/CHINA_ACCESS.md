# 中国大陆访问验收

状态：`REQUIRED_BEFORE_BUSINESS_DEMO`

目标：老杨在天津使用普通国内网络，不开 VPN，也能直接打开商务 Demo。

## 默认拓扑

商务 Demo 默认：

```text
medradar.dpdns.org
  ↓ public DNS
境外源站（优先香港 / 东京 / 新加坡）
  ↓ HTTPS
Caddy
  ↓
静态 H5
```

第一轮验收默认 **DNS-only 直连源站**，不把 Cloudflare 免费全球代理作为大陆可访问性的前提。

原因：普通跨境 Cloudflare 全球网络并不等于 Cloudflare China Network。China Network 是单独的 Enterprise 服务并需要 ICP。商务 Demo 当前不需要为此增加成本和备案复杂度。

## 服务器优先级

在成本允许时：

1. 香港
2. 东京 / 大阪
3. 新加坡
4. 美国西海岸
5. 现有美国 Google VPS 只作为零新增成本测试方案

服务器不在中国大陆时，不依赖大陆 CDN，不把 ICP 作为 Demo 前置条件；但实际访问质量必须用国内网络实测。

## 前端硬要求

Demo 首屏不得依赖以下外部运行资源：

- Google Fonts；
- jsDelivr / unpkg / cdnjs；
- Google APIs；
- `*.vercel.app` / `*.pages.dev` / `*.workers.dev` 作为运行时依赖；
- 外部图片、字体、脚本作为首屏必需资源。

React、图标、CSS、字体策略全部随构建产物本地提供或使用系统字体。

Demo 中出现的“官方依据入口”只是产品交互示意，不能成为页面加载依赖。

## 发给老杨前的真实验收

至少完成以下测试：

### A. 国内手机流量

关闭 Wi-Fi、关闭 VPN，用中国移动 / 联通 / 电信任一手机网络：

1. 打开 `https://medradar.dpdns.org/`；
2. 首屏正常出现；
3. 刷新 3 次无白屏；
4. 打开 TOP1 详情；
5. 返回首页；
6. 生成一条 Demo 沟通话术；
7. 执行“已联系”；
8. 执行“重置演示”。

### B. 第二条国内网络

至少再用另一运营商或家庭宽带重复：

- 首页；
- TOP1 详情；
- 刷新；
- 返回。

### C. 无 VPN

验收全过程必须确认：

```text
VPN / Clash / WARP / 全局代理 = OFF
```

否则结果无效。

## 通过标准

发给老杨前至少满足：

- 2 条独立国内网络均能访问；
- HTTPS 无证书警告；
- 375px 手机宽度无横向滚动；
- 首屏不因外部 CDN/字体失败而残缺；
- 刷新不会 404；
- Demo 明确显示“演示数据”；
- 虚构项目不跳转成真实政府采购公告；
- 公开依据不足的项目不能生成话术。

任何一项失败，都先修复，不把链接发给老杨。

## 如果美国 VPS 访问慢

不要先换前端框架，也不要先加更多 CDN。

处理顺序：

1. 换到香港 / 日本 / 新加坡源站；
2. 保持相同 `medradar.dpdns.org`；
3. DNS A/AAAA 切新服务器；
4. Caddy 重新签发/续用 HTTPS；
5. 重新做两条国内网络验收。

因此域名与产品代码不需要重做。

## Cloudflare

后续可以测试 Cloudflare proxy，但它是可选优化，不是 Demo 的前置依赖。

如果开启后国内访问反而变慢或不稳定，直接退回 DNS-only。

真实商业化后若需要中国大陆 CDN/节点，再单独评估 ICP、国内云或 Cloudflare China Network；不要在商务 Demo 阶段提前承担这套成本。