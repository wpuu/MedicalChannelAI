# 双时段候选独立审查（2026-10-03）

审查范围仅限 `wpuu/MedicalChannelAI`，基线 PR #75 HEAD `3af6db8c678c6f20f8b9d120badd7db102b9d69e`。本文件记录工作区冻结源的审查，最终提交号与 CI 由父任务提交后补充到主证据清单。未读取缺失的旧 patch 或所谓 85 项旧测试证据，不能据此认定历史验证已恢复。

结论：代码可以保存为**有条件发布候选**。这里的同周期幂等依赖生产 Queue 的唯一消费者组和实际 push 串行派发；不是 RuntimeCache 原子锁或任意并发下的幂等证明。上线前必须读回控制面并完成下列门禁。本轮未合并、部署、创建 Preview、恢复 Cron/消费者、清空队列、触发采集或模型。

## 独立验证

- 冻结后独立运行 `python -m unittest discover -s web/pipeline/tests -p test_twice_daily_search.py -v`：25 项通过。覆盖早午独立、首启时钟、小时抖动、串行重投、live/stale RUNNING、旧周期写入拒绝、旧版本/旧日期积压拒绝、缺 canonical 拒 seed、关闭增量链、串行配置及重复 SDK key。
- 实际 `collector-run.handler.do_GET` 离线检查（未替换 `_enqueue_start`，真实运行本地 asyncio，仅 Queue `send` 与 RuntimeCache 为本地替身）：未认证 403；有效认证但缺 period 400；incremental 409；morning/noon 分别 202；已被 Queue 接受的重复 key 返回 202 / `ALREADY_QUEUED`，未误报 503。共三次本地 async send，零真实采集/模型调用。此为请求边界行为检查，不另计入新增测试数字。
- 离线 publish 反例：模拟早间 durable 接收后 active lease 与两份缓存切换到午间。旧 publish 抛 `COLLECTOR_CYCLE_SUPERSEDED`，报告 `durable_accepted=True`；rollback fencing 保留午间 published/latest 缓存，二者均未被旧值覆盖。
- 离线完整父消息重投反例：父 stage 已完成，下一 stage 已入队，但父消息 ACK 未成功。重投返回 `ALREADY_COMPLETED_TODAY` 后下一 stage 的 `send` 抛 `DuplicateIdempotencyKeyError`；当前 worker 正常返回供 SDK ACK，未转成 500。
- 初审发现 `_prepare_stage` 两个并行 delivery 同时首次读取 META 缺失时仍会执行两次采集；用 `threading.Barrier` 复现两次模拟 `_run_ccgp` 与两个 200。该缓存竞态**未被声称修复成 CAS**。候选改为 `maxConcurrency=1` 的 provider push 派发硬条件，lease/retry 360 秒大于函数 `maxDuration=300` 秒；绕过该派发条件的调用仍不能视为安全。
- 独立读取官方 [Queue concepts](https://vercel.com/docs/queues/concepts) 确认并发上限限制 consumer group 同时在途消息，达到上限后等 ACK 或 lease expiry 才再派发；读取 [Python SDK](https://vercel.com/docs/queues/python-sdk) 确认 `max_concurrency` 是 push dispatcher cap、SDK 处理期间会续租；官方 [vercel.json schema](https://openapi.vercel.sh/vercel.json) 包含 `maxConcurrency`、`maxDeliveries`、`retryAfterSeconds`。这些文档不能代替实际线上配置读回。

初审所见只按日期判重、旧 stage 缺少 mutation fence、长暂停全部缓存逐出后可能退回旧 seed、旧 RUNNING 长期阻止恢复，均由本候选周期 ID、写入所有权检查、scheduled context 禁 seed、实际 wall clock 360 秒过期逻辑处理。保留既有 durable monotonic/version-conflict、完整来源覆盖、失败旧快照保留、canonical 门禁与 AI snapshot 版本绑定。未新增来源、地区、架构或付费资源。

## 必须满足的线上门禁

1. 读回实际套餐与免费 Cron 数量/精度限制；确认两个各每日一次的表达式获支持。08:20、12:20 北京时间仍是候选小时触发时段，不保证精确到分钟。
2. 保持 Cron 和消费者暂停，确认候选部署对应唯一受信任 group、唯一活动消费部署及 topic；禁止旧部署/其他 group/手动 pull 同时写同一 canonical。读回 `maxConcurrency=1`、`maxDeliveries=3`、retry 360 秒、lease 360 秒与 maxDuration 300 秒；配置未知或偏离时不得恢复。
3. 读回在途任务、延迟消息和 retry；等待所有旧函数退出，先隔离旧消费者部署。候选按 `schedule_version` 和日期拒绝旧积压，不需要清空队列；未知或匹配旧 active lease 也不绕过版本/日期门禁。
4. 检查完整 canonical 历史是否仍在；任一 shard 缺失不得用旧 seed、空数组或固定 snapshot 冒充恢复。需另有可核对的完整历史恢复证据，再允许受控新周期。生产 DB 最新 verified snapshot 与 reader 缓存要保留和比对。
5. 合并/发布前后及回退后核验生产 deployment/commit、Cron暂停状态、唯一consumer及上述派发值、canonical完整性、durable最新 snapshot时钟/哈希、reader缓存、coverage和AI绑定。先只允许一个当前有效命名周期，失败即暂停入口及消费者并保留旧数据；恢复依据主恢复清单。回退到已知会自动续15分钟链的旧版本时，必须继续暂停 Cron 和消费者，不得同时恢复入口。

实际生产套餐、Cron/队列控制面、canonical持久完整性、真实两周期采集发布和域名/国内访问均未由本独立审查验收；候选通过离线测试不代表每天两次搜索已经恢复。

## 冻结源 SHA-256

| 文件 | SHA-256 |
| --- | --- |
| `web/collector_schedule.py` | `f6e7eea542533b6fbd043d216007255aae279b9ad23d79729ae55d32fb71d74b` |
| `web/collector_runtime.py` | `3c8cd26d4d48d88e1d7e1e2b192d9d4d7054417740f3e054c938e650a0733573` |
| `web/collector_queue.py` | `dd731cd3e03fe1226a6376da5950c821756b96532ac6d2b67eccf7eb96ecc5e9` |
| `web/collector_namespace.py` | `3c13e6ecbcf9cc8b848cf15e85128210e0d05bd1b489c80b35a61ab817f966b7` |
| `web/api/collector-run.py` | `c4209f3e3e66ae72a5cb2fff52d79272312044b26be76af4ecfc398f47316cac` |
| `web/api/collector-queue.py` | `2957444751a170cd4b5ad8d39203aa9a4c3344a600010f209153d45bdb718417` |
| `web/vercel.json` | `07f9a1b84119cfdfc3eb6c9657ac3c78d73385a0e8ffc2363126f29fe7dfe764` |
| `web/pipeline/tests/test_twice_daily_search.py` | `8508fecf0bb01b92814e5f2d6b222a944459f86f36d4f3a4d7f6a7402e5487f3` |
