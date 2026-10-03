# 双时段候选续办独立审查（2026-10-03）

审查范围仅 `wpuu/MedicalChannelAI`。起点为实际本地 HEAD `4038b5d1597d57277e67ea1d86fc40a05233223a`。本审查只读产品源码与已有证据，仅写本报告及新增离线竞态测试；未提交、推送、部署、恢复 Cron/消费者、清队列、触发实际采集或模型。原 patch、85 项旧日志及此前保存的 DATABASE 响应在本环境缺失，未读取或重新声称完成真实响应重建。

## 实际审查范围与证据

- 阅读 `web/collector_schedule.py`、`web/api/collector-run.py`、`web/collector_queue.py`、`web/api/collector-queue.py`、`web/collector_namespace.py`、`web/collector_runtime.py` 的时段入口、周期 ID、消息门禁、stage 重试、canonical 写入、published baseline、历史 reader、投影、durable/cache 提交与回滚路径。
- 阅读 `web/vercel.json`、`web/api/_verifiedSnapshot.js` 和 `web/collector_incremental_runtime.py` 中串行消费、partial durable 基线匹配及旧增量 staging 清理的相关行为。
- 阅读 `test_twice_daily_search.py` 及既有 namespace/native/incremental 文本合约的相关断言，复用本目录 `independent-review.md`、`independent-history-review.md`、`independent-projection-review.md`、定向日志和 canonical audit 的历史证据。
- 阅读 README、current-state、checkpoint 和 `twice-daily-release-20261003.md`，核对候选/生产区分、恢复与回退顺序、验证数字及审批边界。
- 本轮独立运行 `python -m unittest discover -s web/pipeline/tests -p test_twice_daily_search.py -v`：原 35 项通过（0.624 秒）。未重跑全部历史矩阵；此前 native 20 项及完整 CI 是既有/父任务证据，不描述成本审查重新执行。

## 新发现：旧终点可删除新周期 lease

`4038b5d` 的 `_release_active_cycle_if_owned` 使用 RuntimeCache 的 `get` 后 `delete`，无 CAS。Queue 的 `maxConcurrency=1` 仅串行 Queue handlers，不串行独立的 Cron 入口。早间 publish 已标记 COMPLETED 后，午间入口允许开始；以下交错成立：

1. 旧早间终点 `get(ACTIVE_CYCLE_KEY)` 得到早间 lease，尚未 delete。
2. 真实 `_enqueue_start('OFFLINE', 'noon')` 在真实入口逻辑内写入午间 lease，并通过本地 send 替身接受午间消息。
3. 旧早间终点继续 `delete(ACTIVE_CYCLE_KEY)`，删除午间 lease。

用 `threading.Event` 控制上述交错、MemoryCache 和本地 AsyncMock Queue send 独立复现，输出 `noon_queued=prod:2026-10-03:noon:twice-daily-v1`、`active_after_old_release=None`，零真实 Queue/采集/模型调用。午间消息随后会遇到 missing lease，不能把 Queue 串行 cap 当作此入口竞态已被修复的证明。这是需要修复并增加边界测试的候选阻断；已有 35 项均通过却未覆盖该交错。

## 文档与发布顺序

两处旧注释需要纠正：schedule 注释将实际 08:00–10:00 / 12:00–14:00（右端不含）容差写成 :20 后 59 分钟；Queue 终点注释仍声称 degraded 周期启动 intraday chain，而代码已禁用该链。仅改这两处注释不会改变执行逻辑，但上述 lease 竞态修复属于产品行为修改，应单独披露和验证。

发布清单原先先要求两个周期均验收后恢复 Cron，而审批只包含单一当前周期受控采集，顺序不完整。父任务提出的顺序可执行：全部前置硬门禁满足并获同一次明确批准后，合并指定 CI 成功 HEAD、只产生一次 Production 部署；先核对部署/读路径，恢复唯一新串行消费者并隔离旧积压；仅受控启动一个当前周期。该周期通过后按本次批准范围恢复两条每日 Cron，观察另一时段自然触发。两个独立周期均通过配置刷新门禁、准确 partial 范围及页面/durable/cache 同版本验收后才可称每天两次恢复；失败立即暂停两条 Cron 与所有消费者，不补跑第二次手动采集。

回退须先暂停 Cron/全部消费者、等旧在途结束，保留积压与最后已验证数据，再回退已记录 READY 部署的代码/别名；不得自动回写旧数据库版本或恢复旧 15 分钟链。新旧消费者重叠、实际 plan/Cron/queue 状态、canonical 完整恢复、durable/cache 读恢复及国内访问仍是线上未知项。未满足控制面与 canonical 硬门禁时不能合并发布或恢复搜索。

## 增量修复验收

父任务已作最小产品修复，独立读取确认：历史 release hook 不再读取或删除 ACTIVE；结束 marker 保留到下一周期入口替换或 TTL 到期。消息匹配先检查同周期 publish 的 COMPLETED / terminal FAILED / terminal BLOCKED 状态，已结束消息直接确认，不再运行 stage、发送后续或重复清 staging。父任务同时纠正上述两处注释；注释修改自身不影响执行，但 release 与 ended-message 修改明确属于行为修复。

本审查新增 `web/pipeline/tests/test_twice_daily_terminal_race.py`，直接运行实际 `process_collector_payload` 的 publish 终点与实际 `_enqueue_start` 入口，仅 stage 结果、RuntimeCache 和 send 使用离线替身。两项测试通过（0.004 秒）：当前终点不删除午间 lease；同一交错装入旧 compare-delete hook 时确实丢失午间 lease。另单独将当前“不得删除午间”测试套入旧 hook，独立结果为预期的一项失败：`None != 'prod:2026-10-03:noon:twice-daily-v1'`。旧代码失败与新代码通过的对照未修改产品文件、未发真实请求。

修复后独立重跑 `test_twice_daily_search.py`：37 项通过（0.600 秒），包含父任务新增两项：COMPLETED / terminal BLOCKED 的结束 marker 保留后午间真实入口可替换；三种已结束状态重投不运行 stage、不清 staging、不发送 Queue。此次独立必要验证共 39 项通过，另有一项明确预期的旧代码失败，不能将预期失败计入当前候选失败。没有重跑历史全部矩阵。

结论：本次发现的旧终点删新周期 lease 问题已修复并有能复现旧实现失败的边界测试。未发现其他必须在本轮实现的产品阻断，可集中保存为有条件候选。RuntimeCache 仍无 CAS；本修复仅消除上述 compare-delete 操作，**不证明任意并发入口/handler 的全局原子性**，实际唯一 Queue 消费组、串行 cap、租约与旧部署/在途排除硬门禁继续有效。最终远端提交与其正常 CI 仍须父任务读回，不能用本地 39 项取代。

| 冻结文件 | SHA-256 |
| --- | --- |
| `web/collector_queue.py` | `afb693249f06f7da4b5ea5267a2c3ad05fb768bea5903874448a41992d854ccb` |
| `web/collector_schedule.py` | `10fd11f1efb67901f3e859ad4f0a7a566359977d04b2da957e7c4ce5493069eb` |
| `web/pipeline/tests/test_twice_daily_search.py` | `3b62d89005e3b10e5c9dae80215970a027df8f64d6f5b3bac832e8139e08b2b3` |
| `web/pipeline/tests/test_twice_daily_terminal_race.py` | `3e23c04adbb98ef5cb27ba6f0686e755cf22634ed87e2657236c8ff0bacd14ab` |
| `web/collector_runtime.py`（逻辑保持起点版本） | `e62b43e35a52f3cefe3ce5b3cb70480ab983c852757feb7a5d56c82c771f6d87` |
