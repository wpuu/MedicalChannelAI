# 下一轮：最小get-only接入守卫（仅本地注入transport）

推荐GPT-6.1 Sol高（high）；实际运行模型/思考等级未核实。

继续MedicalChannelAI。先核对 /workspace/MedicalChannelAI-p0 最新HEAD、未提交改动和在途工作。读取用户最新指令、docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、ccgp-readonly-integration-review-2026-11-06.md及ccgp-readonly-export-2026-11-06.md。本轮审查起点43a9007，成果见当前HEAD；内核9781921未改。冻结验证器本轮通过，1007/10/3是代码绑定历史门禁，未重跑全套。真实接入和迁移仍NO-GO，不再重复写同一接入审查或重建dry-run/模拟引擎。

实现审查报告中必要的最小接入守卫，仅包装现有observe_d_canonical并注入明确标为SYNTHETIC_LOCAL_STUB的本地只读transport；不导入/构造原生SDK，不启用真实后端模式。复用现有58键清单和d scope校验，拒绝任意键、双epoch前缀、旧c/Production/跨范围；必须在transport读取前拒绝。物理键转发时保持原样，不重新加epoch或剥除前缀，不调用bootstrap/reconcile/调度帮助函数。

加入最多116次get、零重试和可注入monotonic绝对deadline。按已审定拟定上限：从执行启动计总120秒、读阶段110秒，单次timeout不超过2秒和读阶段剩余预算；到110秒不再读取且超期返回拒绝，结果交付前再检查总deadline，过期结果整份拒绝。不能用线程future超时假称已取消底层调用，不能声称守卫能抢占任意卡死的同步SDK；真实transport/硬截止能力仍未核实，真实接入继续NO-GO。仅本地桩模式与scope_provenance_verified=false保持明确，不把外部dict当已认证身份。

验收使用假时钟，禁止真实sleep/网络：正确单前缀原样转发；双前缀/非法键/跨范围零读取；第117次拒绝；开始前、读取中返回过期、结束前deadline耗尽均拒绝且无部分成功；timeout预算正确、无重试/写调用；合法空不回填。已有冻结验证器和相关回归保持通过；代码变化后跑必要回归，保持10/3门禁及原始数据/冻结证据字节不变。输出始终apply_allowed=false、migration_usable=false，不改变内核封套/dry-run输入种类。

权限：仅现有隔离分支的离线代码、必要测试、文档和本地artifact。不新建环境/数据库/角色，不改计划/变量/凭据/权限，不访问或部署云端、不推送、不新增HTTP路由、不实例化真实缓存、不触发采集或项目模型，不写数据库、运行缓存、原始数据或公开快照。前台20分钟。

结束时更新状态、证据和下一轮完整任务，报告实际完成、验证与未完成项。本守卫完成后不再叠加重复模拟层；真实接入仅待明确新增授权、可信SDK/身份/执行通道证据，缺失时不能自动用本地样本替代。当前界面无真正底部提示词提交按钮时，明确说“当前界面无法生成该按钮”，给完整可复制提示词并注明推荐等级和实际设置“未核实”。
