# 最小get-only接入守卫（仅合成本地transport）

2026-11-06，北京时间21:50:24开始，前台截止22:10:24。起点78bb17b，工作树干净；仅根代理运行，无附着终端任务。读取最新用户指令、工作约定、current-state/checkpoint、next-task及两份只读内核/接入审查报告，复用9781921内核。新增守卫代码 **605ebad99041a3057189a1315adae6cc2a773055**；应用采集路径、原内核、dry-run和模拟器未改。

## 实际实现

[collector_readonly_guard.py](../../web/collector_readonly_guard.py)仅增加`SyntheticGetOnlyGuard`及包装函数`observe_synthetic_d_canonical`。transport必须显式声明input_kind=SYNTHETIC_LOCAL_STUB和准确d target_scope；调用者scope、expected_scope及transport声明都须匹配既有内核范围。未标记、真实后端模式、缺标识、跨项目/周期/Production/数据库或具备写能力的对象，在第一次transport.get前拒绝。

复用内核58键清单和epoch_key构建单前缀物理键白名单，固定两遍顺序。每次仅把当前物理键原样转发给transport.get(key, timeout_seconds=...)，不追加/剥除前缀。任意键、双epoch、旧c、Production、快照键和允许键的错误顺序均在转发前拒绝。最多116次get，失败尝试也占次数；第117次不转发。每次调用前、返回后和最终交付前重新检查transport标记/声明，避免声明在运行中变化后仍交付成功。

从守卫启动的monotonic值计算绝对读截止+110秒、总截止+120秒。每次timeout=min(2秒,读阶段剩余预算)，到达读截止不新读，返回时再次检查读截止和单次timeout。读完后的内核校验/封套生成可以使用剩余处理时间，总截止之前才允许交付；等于截止也拒绝。时钟非数字、NaN/Inf、倒退或无法表示截止区间均失败关闭。

首次拒绝使守卫永久关闭，捕获异常不能继续读取或finish；成功finish也关闭。最终必须完成116次调用且未超总截止，否则整份拒绝，不返回部分封套。transport异常不重试，替换为安全固定错误码，不暴露原始异常消息。内核既有版本/owner、大小和内容校验继续生效，未另建校验引擎。

## 输出与边界

包装函数直接返回原内核封套，不增加或修改input_kind/schema、覆盖度、hash或dry-run输入种类。合成本地transport的标记与scope仅为测试对象声明，**不是后端身份认证，也不是任意Python函数的安全隔离**；scope_provenance_verified、apply_allowed、migration_usable始终false。

本守卫传递timeout并在调用返回后检查时间，**不能抢占卡死的同步transport**，未实现线程/子进程取消或平台硬截止。假时钟验证证明的是预算计算与拒绝行为，不是实际120秒硬终止能力或性能SLA。真实SDK、后端身份、执行通道、取消/响应流上限和真实执行回执仍未核实；真实只读接入与迁移保持NO-GO。

## 验证

- 新增24项行为测试，使用假时钟，不用真实sleep/网络。覆盖正确转发、空状态不回填、缺/跨scope及真实模式零读取、非法/双前缀/快照键零读取、第117次、乱序、开始前超期、单次晚返回、读截止、交付截止、119.5秒处理阶段可完成、timeout余量、异常无重试、运行中标记/范围变化、失败后不可继续、时钟错误及原内核拒绝传播。
- 在web/pipeline执行`python -m unittest discover -s tests`，**1031/1031通过**；冻结模板**10/10**、原CLI正反例**3/3**本轮重放通过。CLI复现仍隔离event-watch为空，不替代完整事件语义验收。原只读内核冻结验证器通过；其1007日志属于旧证据，本轮实际完整回归为1031。
- [本轮离线验证器](validation/ccgp-readonly-guard-2026-11-06/verify.py)直接复用既有冻结recipe/fixture构造合成transport，在RuntimeCache构造、网络和sleep阻断下运行守卫。真实官方记录只来自原两条仓库样本；缓存存在性、owner/健康时钟及运行时长仍是明确合成外壳，不代表云端数据。
- 守卫前后正常封套SHA仍`a3b86c23c2e74601cbbd7e70fff407a73a3aa0162423da1d9c12a4eaa344218b`；未初始化封套SHA仍`08b0e23e2a234738df81cac084953af903828fe2e12d7d9abb575a6be7892376`。重复输出完全一致，116条逐键调用轨迹和2秒timeout可重放，桩值不变。
- 起点下**305份**data、fixtures及旧validation文件字节不变，原内核、解析/生成器/模拟器未改。新证据见[manifest](validation/ccgp-readonly-guard-2026-11-06/manifest.json)。没有新建环境、修改计划/变量/凭据/权限、访问云端、部署、推送、触发采集/项目模型，未写数据库、运行缓存、原始数据或公开快照。

## 阶段结束与下一步

本轮授权的离线守卫阶段已完成，不再叠加重复模拟/审查层。下一项必要工作是**一次现有d环境的云端只读元数据核实**，只确认项目/Preview部署来源、已存在的身份/SDK/执行通道证据，不运行缓存读取或业务函数；见[next-task.md](next-task.md)。由于用户本轮明确“不访问云端”，该步骤须获得后续明确的新授权，本轮没有执行。用户仅说“继续”时不自动扩大到云端，也不制造额外离线工程任务来代替缺失授权。

状态与下一轮完整提示词已更新。当前界面无法生成该按钮；给可复制提示词。推荐GPT-6.1 Sol高（high），实际运行模型/思考等级未核实。
