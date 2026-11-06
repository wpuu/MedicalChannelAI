# 下一轮：返回主线，离线审查共享官方入口限流与重试预算（仅文档）

推荐GPT-6.1 Sol高（high）；实际运行模型/思考等级未核实。

继续MedicalChannelAI。先核对 /workspace/MedicalChannelAI-p0 最新HEAD、未提交改动和在途工作，读取用户最新指令、docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md及ccgp-runtime-integration-decision-2026-11-07.md。最新成果见当前HEAD；原守卫605ebad、内核9781921未改。SDK真实接入分支已以NO-GO关闭，不重新审计同版SDK、不追加模拟、不查云端或请求宽权限。

返回current-state中已登记尚未完成的“入口共享预算/冷却”主线。读取docs/project/event-diagnostics-retry-2026-11-06.md、source-recovery-precision-2026-11-06.md与web/collector_runtime.py、web/collector_incremental_runtime.py、web/pipeline/medical_channel_pipeline/ccgp_discovery.py、ccgp_detail.py、web/pipeline/scripts/sync_regional_ccgp.py及相关既有测试（含test_collector_deferred_budget.py）。先核对已完成的终局重试/降级修复，避免重复报告。

仅静态追踪共享官方host的请求调用链、timeout/重试/Retry-After/冷却、阶段与总预算传递；判断并发来源/地区是否会各自重试同一入口、是否将限流误当采集完整、预算耗尽是否仍多等。最多给3项有最新源码行号和既有测试/冻结证据依据的问题及优先级，不凑数。没有复现证据的只称静态设计缺口或待验证，不能当已确认线上bug；不把历史7/14、8/14健康或旧403/限流当当前状态。

验收：输出请求调用链和已有机制/缺口对照、已修不重复项、最多3项最小修复建议（准确文件/触发条件/预期行为/后续验收）。不写修复代码、不新增mock/测试引擎、不修改原始数据或冻结证据。若已有代码已覆盖则给证据并关闭，不制造新任务。

权限：仅现有隔离分支本地源码/既有证据只读与文档/验收artifact更新。不联网、不安装/导入/执行SDK、不查项目元数据、凭据、环境值或日志，不调用业务接口、RuntimeCache、数据库、函数/Queue/模型，不新增环境/路由、不改应用或锁文件、计划/权限/保护，不部署、不推送、不写运行数据。apply_allowed=false、migration_usable=false。前台20分钟。

结束时更新状态、证据与下一轮完整任务，报告实际完成、验证和未完成项。当前界面无法生成真实底部提示词提交按钮时如实说明并给完整可复制提示词，推荐等级及实际设置未核实。
