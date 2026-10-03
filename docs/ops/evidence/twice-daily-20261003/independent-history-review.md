# 已发布历史遗漏门禁：独立增量审查

日期：2026-10-03。范围仅 `wpuu/MedicalChannelAI`，审查父任务冻结的 `_require_published_canonical_history` 与相应边界测试。未修改产品代码；未恢复线上 Cron/消费者、写数据库或缓存、运行采集/模型、部署或创建 Preview。之前独立审查的八文件哈希描述此前冻结版，本次 runtime/test 变更以本报告哈希为准。

结论：新增门禁正确阻断已复现的历史 ID 遗漏，可保存到候选版。它是必要的保守门禁，**不是 canonical 完整恢复证明，也未批准线上恢复**。实际套餐、Cron、消费者及在途/延迟 retry 状态仍未验收；原独立审查要求的 provider 串行消费控制面门禁继续有效。

## 独立实证

从本地 Git 对象 `62299590dd3898e040ccc9db5fda1298d4509d51` 读取九份生产 live canonical 数组，合计 911 条。按当前 `_run_publish` 读取范围取出 903 条，与保存的生产 GET `/api/public-snapshot` 响应中的完整 441 条 pool 比较，确实缺少以下四条已发布 ID：

- `tjzyefy_intent_20260804_030195986`
- `tjzyefy_intent_20260804_030195988`
- `tjzyefy_intent_20260804_030195991`
- `tjzyefy_intent_20260804_030195992`

同一份真实保存 baseline（`snapshot_as_of=2026-10-02T14:19:15.713282+08:00`）代入新增 helper：903 条集合被 `COLLECTOR_CANONICAL_PUBLISHED_HISTORY_MISSING` 拒绝；911 条集合只通过 ID 子集检查。此通过没有写入线上 canonical，也没有把公开卡片反造为 canonical。

独立运行当前 `test_twice_daily_search.py`：30 项通过，其中新增五项检查缺 baseline、缺 top cards 以外的历史 ID、坏 pool/重复 ID/错误 count、baseline 时钟、过期记录保留；独立运行 `test_collector_native_reliability.py`：20 项通过。只重跑此次必要相关范围，未重复历史矩阵。

代码按 scheduled ContextVar 强制显式 `opportunity_pool` 和对应整数 count，逐项拒绝非法/空白/重复 ID，不回退 `cards`，不静默过滤坏 pool；baseline 时间须可解析、带时区且不晚于本周期。历史 ID 比较使用原始 canonical 集合，在生成新 snapshot 和任何 durable/cache publish 前执行。缺 baseline/缺 ID 的测试验证 builder/durable publish 均未被调用，并保留原两份快照缓存。

另以真实历史 `ccgp_4bfa39429a3845a3` 做离线过期边界：仅在测试计算中使用 `2027-01-01` 时钟，完整原 canonical 记录仍通过历史 ID 门禁，但正常 builder 将其从当前 pool 排除。没有发布或持久化该模拟时钟，不能把此测试当作自动更新。

## 静态历史重建与 runtime 的证据界限

独立完整复跑：

```sh
python docs/ops/evidence/twice-daily-20261003/reconstruct_historical.py \
  --baseline .medicalchannelai-onboarding/schedule/canonical-audit/durable-public-snapshot.json
```

脚本只读 Git 生产 live 数据与已保存 GET 响应，使用当前静态发布组合流程：`load_arrays` 增补天津市场元数据、天津及其 events 与 regional 分开构建、`combine_snapshots` 注入市场字段并对全池复排。911 条输入在真实历史 as-of 重建出 441 条，逐 ID 全字段比较 `different_card_count=0`；baseline 文件 SHA-256 为 `14a3d2d7924edc1e55656f1f5a58b1e5f90daa97c97e9dd69ef10fb8f`。脚本明确 `candidate_runtime_recovery_verified=false`、无网络/生产写入。

独立最初用裸候选 `runtime.build_public_snapshot` 重建时，441 个 ID 都一致，但 441 条 facts 缺少生产公开投影的 `market_code`、`market_name`、`market_admin_code`，235 条 rank 不同。裸生产版本 builder 也不包含上述静态组合步骤。该差异说明静态历史全字段复建不能证明当前 `_run_publish` 可等价恢复；本次新增 ID 门禁没有解决投影组合差异。

保存 GET 响应的历史重建也不是本审查直接读取数据库/RuntimeCache 的证据。恢复前仍需读回真实 durable baseline 与 canonical/cache inventory，核对来源、哈希、数量、完整历史及投影字段；禁止以空数组、旧 seed 或固定 snapshot 冒充自动更新。合法空 baseline 可通过纯结构检查，因此运营恢复必须核对实际已发布的 441 条基线，不能以手造空 pool 绕过。

已发布 pool 只代表当前公开投影，不覆盖所有 911 条归档历史，更不证明暂停后所有新增事实都已取得。未读的既有三来源文件八条 canonical、四条当前已发布 intent 以及静态/runtime 投影差异仍属恢复前待解决项；不因此扩展来源地区或更换架构。控制面与完整恢复证据未满足时应继续暂停入口和消费者。

## 本次冻结 SHA-256

| 文件 | SHA-256 |
| --- | --- |
| `web/collector_runtime.py` | `f0364cf145a2632547d4cb4fe5502c301d1e81e7b3e673bb197b2d7785bead61` |
| `web/pipeline/tests/test_twice_daily_search.py` | `0dffd9d245c4888d8116ff1d3a940124a2176a2a1e25911bccdd48e6e44faefc` |
| `docs/ops/evidence/twice-daily-20261003/reconstruct_historical.py` | `8b6ab893788d79d4f6002949ec0d34c10a12c1a97e0f0fceb656386294e5dea4` |
