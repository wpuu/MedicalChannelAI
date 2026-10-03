# 既有历史分片与市场投影：独立增量审查

日期：2026-10-03。只审查 `wpuu/MedicalChannelAI` 本轮冻结的历史 reader、scheduled 投影及 partial coverage 变化。只写本报告，未编辑产品源码。未部署、恢复 Cron/消费者、写线上缓存/数据库、触发真实采集或模型。

结论：新增 reader 与投影修复可以保存为候选。三个独立 v2 key 只保留已存在的 `tjzxfc`、`tjzyefy`、`tjzyefy-intent` 历史，没有新增采集 stage、网络入口或来源地区。原已复现的四条 intent 遗漏与市场字段/235 条 rank 差异在离线真实资料重建中已解决。**这不等于线上恢复通过，也不构成发布就绪声明。**

## 独立检查结果

- 冻结后独立运行 `test_twice_daily_search.py`：35 项通过；`test_collector_native_reliability.py`：20 项通过。仅重跑受本次修改影响的必要范围。
- 脱离可被 prebuild 改写的 bundled fixture，直接 `git show 62299590dd3898e040ccc9db5fda1298d4509d51` 读取生产九份 live canonical（911 条）及 events，使用已保存 GET 响应的真实历史 as-of `2026-10-02T14:19:15.713282+08:00` 调用新 `_build_scheduled_public_snapshot`。结果完整 441 条 `opportunity_pool` 与保存的生产 GET 响应逐条全字段相等；四条原 intent 保留，市场字段与全池 rank 相等。没有新采集或发布该历史快照。
- `_preserved_source_history` 只读取三份独立数组、做 schema/source-prefix/TJ 校验。缺 key、非数组、非法 record 或错误来源拒绝；不从 Git、bundled、seed 或卡片 bootstrap。原已发布历史 ID 子集门禁仍在新投影前运行。
- 新投影先检查跨分片 ID 唯一，区域 metadata 必须存在且合法。明确天津来源集合在深拷贝上补 metadata，原 canonical 保持不变；区域记录不凭缺字段推断为天津。
- 独立同项目编号反例：把一条天津记录与一条区域记录设置为同 project number，仅向天津分组传入本地解析的终止事件。无事件时 pool 有两条，有事件时只移除天津条目、区域条目保留；输入 canonical JSON 不变。该反例没有网络、采集或持久化。
- 独立 partial coverage 反例：本地缓存装入真实 911 条分片，baseline 带已知旧 `last_complete_as_of`，durable 仅使用本地替身。新 snapshot 的 `complete=false`，保持旧完整时间，列出三项 `history_only_source_ids`；原历史数组及 observed_at 未改变，不把历史保留视为刷新成功。
- 独立运行 `node web/scripts/check-partial-coverage-ai.mjs`：PASS，single/batch/cache-only/prewarm 均被 incomplete coverage 门禁阻断，provider/database 请求为零。运行 `node web/scripts/check-publish-preflight.mjs`：PASS，原 partial durable 基线匹配、无效候选禁止写入及并发前进保护继续有效。前端既有 partial 提示与完整覆盖 AI provenance 条件保持适用。

初版投影使用 `setdefault` 时，真实 intent 的三项 TJ metadata 为 null 会被放行并生成三个空字符串；独立反例发现后父任务修复：明确天津集合在 copy 上固定 code 为 TJ，缺失/null/空白 name/admin 补天津值，非空错误 metadata 仍拒绝。新增边界测试通过，canonical 未因此改写。

## Fixture 与恢复限制

`run-prebuild.mjs` 先执行静态 bundled refresh，再执行 Python tests；测试中的 bundled 对照会变成当前静态流程产物。因此该测试用于说明新 scheduled helper 与既有静态组合流程兼容，单独不能证明生产恢复。上述独立生产 Git 对象与已保存真实 GET 响应比较补足了历史投影的验证，不依赖重写后的 fixture。

三个历史缓存须在获准恢复时按现有 published stable-key 约定无主动 TTL 保存，避免只读历史在固定两周后失效；当前 reader 不自动初始化或改写 observation 时钟。RuntimeCache 仍可逐出，逐出后阻断发布，不能伪造空历史来续跑。此要求在恢复文档中列为前置条件，本轮未执行线上恢复。

三个历史来源仍无新的自动监控，本轮只刷新原有受门禁保护的 stages。scheduled snapshot 始终标注部分来源更新，因此自动 AI 门禁会维持限制；不得称所有既有来源均已获得最新完整采集。历史事实投影相等也不证明暂停期间新事实不存在。

实际套餐、Cron 状态、唯一消费者/串行派发值、在途与延迟 retry、线上 canonical/cache inventory 和完整恢复尚未验收。既有 `maxConcurrency=1`、lease/retry 360 秒大于 maxDuration 300 秒、旧部署隔离、真实 durable baseline 读回等发布硬门禁继续有效。条件未满足时保持暂停，不宣称每天两次搜索已恢复。

## 本次冻结 SHA-256

之前报告保留修复前证据及旧版哈希，本次产品投影变化以以下冻结哈希为准。

| 文件 | SHA-256 |
| --- | --- |
| `web/collector_runtime.py` | `e62b43e35a52f3cefe3ce5b3cb70480ab983c852757feb7a5d56c82c771f6d87` |
| `web/pipeline/tests/test_twice_daily_search.py` | `fc510a0d6281605f996ed23a3d8cb957fcfe13bd8ea9de41fc467e18e2f46618` |
| `web/pipeline/scripts/publish_web_snapshot.py` | `d5723712f6c7dc65a62e8c0b6bed30d1e535484d2b4fef24dce0a1218e7deb9e` |
