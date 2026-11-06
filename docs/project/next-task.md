# 下一轮：仅本地复现并最小修复F3区域CLI完整性门禁（需代码/测试修改授权）

推荐GPT-6.1 Sol高（high）；实际运行模型/思考等级未核实。

本轮只做文档审查，F3仍是静态可达缺口、未行为复现，不能称已确认线上bug。下一轮需用户明确授权现有隔离分支的本地代码/测试修改；不扩展云端权限。SDK工作流保持关闭，不再追加模拟层。

收到授权后，先核对 /workspace/MedicalChannelAI-p0 最新HEAD、未提交改动与在途工作。读取用户最新指令、docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、shared-entry-budget-review-2026-11-07.md、action-radar-acceptance-contract.md及ccgp-runtime-integration-decision-2026-11-07.md。成果以当前HEAD为准；守卫605ebad/内核9781921未变，1031/10/3为历史门禁。

只处理F3，不同时实现F1共享冷却或F2墙钟预算。读取web/pipeline/scripts/sync_regional_ccgp.py、publish_web_snapshot.py、.github/workflows/regional-medical-refresh.yml及既有相关测试/冻结官方语料。先用既有unittest和CLI入口，在网络/真实客户端阻断、临时目录中复现“至少一条发现成功，同时其他查询/详情失败仍写records并退出0”的情形；不新增审查引擎，不访问真实来源。若不能复现或发现已修，给证据关闭，不强行改代码。

若确认，最小修改sync_regional_ccgp.py：在records写入前做明确完整性放行；部分scoped/fallback/详情失败、明确限流等不以成功结束，不发布该失败批次的部分新事实；保守第一步允许整批返回非零且保留原records，完整合法空和完整成功仍可成功。失败诊断写安全的显式report，report不得覆盖records/输入。不能把这种保守整批保护说成已实现每市场独立提交/覆盖水位。

验收覆盖真实CLI的全成功、完整空、部分scoped失败、部分详情失败、单条明确限流、全部发现失败和fallback局部失败；检查退出码、报告状态、原records/输入字节不变。候选/报告仅临时目录或新增验收目录，不写仓库原始历史文件/公开快照。代码变化后运行必要回归及10/3门禁，市场/产品解析与runtime单源fail-closed保持不变。不得只用源码字符串断言替代行为验收。

权限：仅现有隔离分支本地离线代码、必要测试、文档和验收artifact。不联网、不安装/导入/执行真实SDK，不查询项目元数据、凭据、环境值或原始日志，不调用业务接口、RuntimeCache、数据库、函数/Queue/模型。不新建环境/路由、不改依赖锁、计划、变量、权限或保护，不改工作流定时、不部署、不推送、不写运行数据/原始历史数据或公开快照。apply_allowed=false、migration_usable=false。默认前台20分钟。

结束时更新状态、证据和下一轮完整任务，报告实际完成、验证、未完成项及静态发现是否已被行为确认。当前界面无法生成真实底部提示词提交按钮时如实说明并给完整可复制提示词，注明推荐等级和实际设置未核实。
