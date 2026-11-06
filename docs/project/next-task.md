# 下一轮：现有d命名空间的只读导出内核（仅离线）

推荐GPT-6.1 Sol高（high）；实际运行模型/思考等级未核实。

继续MedicalChannelAI。先核对 /workspace/MedicalChannelAI-p0 最新HEAD、未提交改动和在途工作，读取用户最新指令、docs/project/working-protocol.md、current-state.md、checkpoint.json、ccgp-memory-simulation-2026-11-06.md及本文件。当前内存模拟代码8f8b5cc，984项Python、冻结10/10、原CLI3/3通过；两条候选整批overlay/回滚恢复892条原状态，重复投递0修改。现有生成器9f6ac31和change_id不变，真实CAS/事务、canonical导出和迁移均未完成。不要重写已完成的解析、dry-run或内存模拟。

增量工作：先阅读 web/collector_runtime.py、web/collector_namespace.py、web/collector_epoch.py、web/collector_incremental.py 与现有导出/状态帮助函数，复用实际键和命名空间规则，实现一个通过注入缓存读接口工作的canonical只读导出内核；仅内部函数和本地缓存桩，不新增HTTP路由，不调用真实Runtime Cache。导出对象包括明确来源分片、canonical、对应事件/健康时钟及pending/barrier/owner版本；先确定哪些数据是现有真实结构，未知字段明确标未覆盖，不能发明完成状态。

范围只允许现有Preview项目及d周期的显式预期标识，缺失或跨周期在任何缓存读取前拒绝。只读接口不得具备set/delete/expire能力。没有canonical时返回有界的空状态或未初始化，不从公开16条快照或仓库892条自动回填；不能读取旧c或Production来凑数据。前后读取的版本/owner不一致或必需分片读取失败时，整份导出拒绝或明确不可用于迁移，不能把部分读到当完整成功。输出须有scope、来源/版本/hash和完整性说明，可供后续受控输入准备，但不改变已有dry-run的冻结输入种类规则。

验收：使用本地只读桩覆盖正常、合法空、缺标识、跨周期、owner/版本变化、部分读取失败、超量/大小限制和未知字段；证明无写调用、无外域/旧周期读取、无公开快照兜底。现有984及相关10/3门禁保持通过，原始数据/冻结证据不变。明确这只是离线导出内核，不是真实canonical导出完成、权限开放、迁移或CAS实现。

权限：仅现有隔离分支的本地代码、测试、文档和验收artifact；不新建环境/数据库/角色，不改计划/变量/凭据/权限，不访问或部署云端，不新增对外导出接口，不触发采集或项目模型，不写数据库/缓存/原始历史JSON/公开快照。默认20分钟。

结束时更新状态、证据与下一轮完整任务。当前界面若仍无真正的底部提示词提交按钮，明确说“当前界面无法生成该按钮”，给完整可复制提示词，不用弹窗或链接冒充，并注明推荐等级及实际设置“未核实”。
