# MCAI-AI-RELIABILITY-001：AI 分析需多次点击才成功

日期：2026-09-28

## 现象

用户反馈“AI 分析点了 3 次才完成一次”。

## 线上复现（Production `8e658b1`，`/api/ai/analyze` 单条，未命中缓存）

| 结果 | 次数 | 耗时 |
|---|---|---|
| 成功 | 8 | 1.9–6.0s |
| `AI_TIMEOUT` | 1 | 24.7s |

同一条超时商机立即重试：9.5s 成功；此后命中 durable cache 0.4s。

## 根因

1. 单次 provider 调用硬超时 12s，超时后**从零重试**，两次合计 24.7s → `AI_TIMEOUT`。10–20s 的长尾正常回答全部被丢弃。
2. `isConnectivityError()` 把自身 `AbortError` 当成网络故障，重试被切到备用 `.cn` 区域，从 `iad1` 访问更慢，重试更易超时。
3. 超时后没有任何结果写入缓存，只能让用户手动再点。
4. `getOrCreateSharedPublicAiBrief` 在模型生成全程持有 DB 事务 + advisory lock（批量 10 条即占 10 个连接）。

## 修复

- Provider：保持首个请求不中断，8s 仍无响应时并行发起 1 个对冲请求（同路由），先返回的有效结果胜出、另一请求 abort；总预算 42s；最多 2 次尝试。
- 自身超时不再切换 `.cn`；仅 DNS/连接类错误切换。
- 一次 `AI_RESPONSE_INVALID`（模型输出未过校验）自动重采样一次。
- `api/ai/analyze.js` `maxDuration` 30 → 60（`vercel.json` 显式声明），总预算留 ≥10s 余量给鉴权/DB，保证生成结果总能写入共享缓存。
- 共享缓存：读缓存 → 事务外生成 → `INSERT … ON CONFLICT DO NOTHING`（先写者胜，冲突时回读胜者），不再在生成期间持锁。
- 前端：单条与批量对 `AI_TIMEOUT` / `AI_RESPONSE_INVALID` / `AI_PROVIDER_UNAVAILABLE` / 网络错误自动静默重试一次；分析超过 10s 显示“系统仍在处理，无需重复点击”。

## 验证

- 新增 `web/scripts/check-ai-provider-hedge.mjs`（已接入 prebuild）：对冲胜出/败者 abort、首请求先返回、总预算超时不切区域、无效样本重试一次、429 立即停止、DNS 故障仍切备用区域、预算 < maxDuration−10s、生成期间不持事务。
- `npm run build`：748 pipeline tests OK，全部 JS 合约检查 PASS。

## 后续（未包含在本次）

- Daily cron 刷新快照后预生成 Today / 商机池 AI 建议，使用户点击直接命中缓存。
- AI 请求按 `snapshot_as_of` 内存缓存快照，避免每次从 Neon 读取 ~1.5MB。
