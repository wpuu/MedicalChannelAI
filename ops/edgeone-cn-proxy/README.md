# MedicalChannelAI 中国大陆入口代理

任务：MCAI-CN-ENTRY-011

用途：使用 Tencent EdgeOne Makers Edge Functions 作为 `medicalai.qd.je` 的公开入口，避免国内浏览器直接访问 `*.vercel.app`。

## 当前实现

```text
浏览器
 -> EdgeOne Makers
 -> V8 Edge Function
 -> medicalchannelai.vercel.app
```

- 根路径 `/` 内部映射到 Vercel 的 `/today`；
- 其他 path/query 原样代理；
- EdgeOne 预览参数 `eo_token` / `eo_time` 不传给 Vercel；
- 浏览器地址保持 EdgeOne / 自定义域名，不做 30x 跳转；
- Vercel 仍是权威业务源站。

## V8 兼容约束

按 TencentEdgeOne 官方 Makers Edge Functions 规范：

- 不使用 `new Headers()`；
- headers 使用普通对象；
- 不使用 Node.js API；
- 不使用 `process.env`；
- 不使用 `Response.json()`；
- 仅使用 V8/Web Standard API。

## 已确认的故障边界

同一 EdgeOne 预览 token 下：

- 静态文件 `/edgeone-placeholder.txt` 可访问；
- 根路径曾返回 EdgeOne 404；
- Vercel `/today` 和 `/api/status` 同时正常。

因此当前故障位于 EdgeOne 路由/代理层，而非预览 token 或 Vercel 源站。

## EdgeOne 项目配置

- Repository: `wpuu/MedicalChannelAI`
- Root directory: `ops/edgeone-cn-proxy`
- Build command: `npm run build`
- Output directory: `public`
- Production branch: `main`
- Acceleration region: `Global (Excluding Chinese Mainland)`

## 验收

新部署后使用完整带 `eo_token` 的预览地址验证：

- `/` 显示 Today 页面；
- `/today` 正常；
- `/api/status` 返回 `ready=true`；
- 静态资源正常；
- AI POST 可正常工作；
- 浏览器地址不跳到 `*.vercel.app`。

通过后再绑定 `medicalai.qd.je`。
