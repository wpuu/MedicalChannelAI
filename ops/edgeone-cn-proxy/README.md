# MedicalChannelAI 中国大陆入口代理

任务：MCAI-CN-ENTRY-010

用途：使用 Tencent EdgeOne Makers Middleware 作为 `medicalai.qd.je` 的公开入口，避免中国大陆浏览器直接访问 `*.vercel.app`。

## 工作方式

```text
浏览器
 -> medicalai.qd.je
 -> EdgeOne Makers Middleware
 -> internal rewrite
 -> medicalchannelai.vercel.app
```

- 浏览器地址栏保持 `medicalai.qd.je`；
- 根路径 `/` 内部 rewrite 到 Vercel 的 `/today`，不做浏览器 30x；
- 其他 path/query 原样 rewrite 到 Vercel；
- EdgeOne 预览参数 `eo_token` / `eo_time` 不传给 Vercel；
- 不再使用自写 Edge Function fetch 代理；
- 不存储 API Key，不包含用户数据；
- Vercel 仍是权威业务源站。

## 为什么改成 Middleware

EdgeOne Makers 官方 Middleware：

- 在项目根目录使用 `middleware.js`；
- 默认可匹配所有路由；
- 官方 `rewrite()` 支持绝对 URL；
- 适合请求 rewrite / routing control；
- 比手写 `fetch + Response` 代理更少运行时兼容面。

## EdgeOne Makers 项目配置

- Repository: `wpuu/MedicalChannelAI`
- Root directory: `ops/edgeone-cn-proxy`
- Build command: `npm run build`
- Output directory: `public`
- Production branch: `main`
- Acceleration region: `Global (Excluding Chinese Mainland)`，当前用于无备案技术验证
- 自定义域名：后续绑定 `medicalai.qd.je`

## 验收

先用新部署预览地址验证：

- `/` 显示 Today 页面；
- 地址栏仍是 EdgeOne Preview，不跳到 Vercel；
- `/today` 正常；
- `/api/status` 返回 `ready=true`；
- 页面静态资源正常；
- AI 请求可正常 POST。

通过后再绑定 `medicalai.qd.je`。
