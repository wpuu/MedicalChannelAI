# AI 情报雷达源站超时缓存回退（2026-09-14）

> 此文档仅记录验证背景与边界，不表示功能已部署到 Production。

## 触发原因

Production TEDA 只读 shadow smoke 中，首次请求约 2.485 秒返回 `AI_REFRESH_PENDING`，68 条官方链接进入后台 Agnes；后台 AI 已成功完成并写入 Runtime Cache。随后第一次轮询因 TEDA 官网自身 `SOURCE_TIMEOUT` 返回 503，第二次轮询在源站恢复后才命中 `SERVER_AI_CACHE`。

这说明已有 READY AI 缓存时，来源站点瞬时不可用仍可能先阻断用户读取缓存。

## 修复边界

- 只允许同一来源签名、同一 `ANALYSIS_VERSION` 的 READY 服务器缓存回退。
- latest resilience cache 会保存并重新校验官方 `anchor_snapshot` 与 `content_fingerprint`。
- `force_ai=true` 不允许回退旧缓存，强制重扫继续 fail closed。
- 源站失败时返回明确状态 `SERVER_AI_CACHE_SOURCE_UNAVAILABLE`，并保留 `coverage_partial=true` 与原始 `SOURCE_*` 错误码。
- 不修改 verified snapshot，不修改商机池，不降低 SSRF/来源安全边界。

## 当前验证

- 定向缓存测试 PASS。
- 完整 Python / prebuild：709/709 PASS。
- TypeScript + Vite production build PASS。
- Vercel 当日免费部署额度已达到平台上限，因此当前修复尚未 staged / promoted；Production 仍运行 PR #18 已验证版本。
