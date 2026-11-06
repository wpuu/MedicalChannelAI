# 下一轮：最小真实只读接入方案与阻断项审查（仅离线）

推荐GPT-6.1 Sol高（high）；实际运行模型/思考等级未核实。

继续MedicalChannelAI。先核对 /workspace/MedicalChannelAI-p0 最新HEAD、未提交改动和在途工作，读取用户最新指令、docs/project/working-protocol.md、current-state.md、checkpoint.json、本文件及ccgp-readonly-export-2026-11-06.md。内核代码97819215530454da55e0d5052b7bfbcd7f9ff694，本轮文档成果见当前HEAD；1007项Python、冻结10/10、原CLI3/3通过。复用内核、dry-run9f6ac31、模拟器8f8b5cc与冻结证据，不重复部署或重写审查引擎。

本轮只审查并产出最小真实只读接入方案，不执行真实导出。读取web/collector_readonly_export.py、collector_epoch.py、collector_namespace.py、collector_runtime.py、collector_incremental.py、collector_incremental_runtime.py及仓库运行缓存/身份适配说明，完成：

1. 明确现有d项目/周期的真实缓存如何仅通过get-only facade进入内核，避免原始键与epoch包装器双重前缀；scope由何种可信运行证据绑定，哪些身份/权限仍未核实。不得读取凭据或访问服务来确认。
2. 明确58键/116次get的固定计划、截止时间/大小预算、owner变化/读取失败/TTL驱逐/缺失分片的处理；核查committed优先级、事件/健康时钟、pending/barrier及共享分片覆盖。保留未知项，不把双遍一致写成原子一致。
3. 区分“限定范围只读观察可执行”与“足以迁移/纠错”的门槛。列出最小阻断项、所需证据、下一次一次性验收的具体步骤与最小权限。生产者没有统一原子revision/fence，不能用方案文字将migration_usable改为true。

验收：产出引用最新代码行号的具体接入方案和go/no-go表；预定只读键与现有58键一致或解释实际差异，写调用0；缺标识/跨周期仍读取前拒绝，合法空不兜底。复核本轮冻结验证器；只有发现并修复实际缺陷时才补必要行为测试并重跑相关门禁。不得为凑进度增加重复校验器、扩大dry-run输入种类，或把合成外壳冒称云端canonical。无真实身份/权限证据时明确标未核实、真实接入未执行。

权限：仅现有隔离分支离线代码（仅确有缺陷时）、测试、文档、本地artifact。不新建环境/数据库/角色，不改计划/变量/凭据/权限，不访问或部署云端、不推送、不新增HTTP路由、不实例化真实缓存客户端、不触发采集或项目模型，不写数据库、运行缓存、原始数据或公开快照。始终apply_allowed=false；不声称真实导出、迁移、CAS或回滚完成。默认前台20分钟。

结束时报告实际完成、验证与未完成项，更新状态、证据和下一轮完整任务。没有真正的底部提示词提交按钮时，明确说“当前界面无法生成该按钮”，给完整可复制提示词，不用弹窗或链接冒充，并注明推荐模型/等级、实际设置“未核实”。
