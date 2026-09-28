# MedicalChannelAI 中国大陆入口代理

任务：MCAI-CN-ENTRY-006

用途：使用 Tencent EdgeOne Pages + Edge Functions 作为 `medicalai.qd.je` 的公开入口，避免中国大陆浏览器直接访问 `*.vercel.app`。

## 工作方式

```text
浏览器
 -> medicalai.qd.je
 -> EdgeOne Pages Edge Function
 -> medicalchannelai.vercel.app
```

- 浏览器地址栏保持 `medicalai.qd.je`；
- 根路径 `/` 内部映射到 Vercel 的 `/today`，不做浏览器 30x；
- 其他 path/query 原样回源；
- GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS 均由同一代理函数处理；
- Vercel 返回的绝对 Location 若指向 Vercel，会改写回 `medicalai.qd.je`；
- 不存储 API Key，不包含用户数据；
- Vercel 仍是权威业务源站。

## EdgeOne Pages 项目配置

导入仓库 `wpuu/MedicalChannelAI` 时：

- Root directory: `ops/edgeone-cn-proxy`
- Build command: `npm run build`
- Output directory: `public`
- Acceleration region: 优先 `Global (Excluding Chinese Mainland)`，不依赖 ICP；
- 自定义域名：`medicalai.qd.je`

必须以 EdgeOne 控制台实际生成的 CNAME 为准，不在仓库中硬编码 DNS 目标。

## 验收

切换 DNS 前先用 EdgeOne 预览域名验证：

- `/` 能显示 Today 页面；
- `/today` 正常；
- `/api/status` 返回 `ready=true`；
- 页面静态资源正常；
- AI 请求可正常 POST；
- 不出现浏览器跳转到 `*.vercel.app`。

通过后再把 DigitalPlat 当前临时 A 记录切换为 EdgeOne 提供的 CNAME。
