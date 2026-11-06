# d周期canonical只读观察内核（仅离线）

2026-11-06，北京时间21:01:01开始，前台截止21:21:01。起点HEAD为246c139，工作树干净，仅根代理运行，无附着终端任务；读取工作约定、最新用户任务、状态/checkpoint、next-task及上一轮内存模拟报告。新增内核和23项行为测试，代码提交为 **97819215530454da55e0d5052b7bfbcd7f9ff694**。本轮只使用现有隔离工作树，无云端访问或推送。

## 实际实现

内部函数 `web/collector_readonly_export.py::observe_d_canonical` 仅接收get-only接口，未新增HTTP路由、CLI或真实客户端。复用collector_namespace的v2常量、collector_epoch.epoch_key和SOURCE_POLICIES；没有调用可能bootstrap、归一化缺失值或写入缓存的帮助函数。区域v3、CCGP committed/staging和增量私有键格式以现有运行函数做行为测试锁定；内核不导入会修改runtime全局命名空间的incremental_runtime。

读取前要求scope及独立expected_scope均准确对应现有项目、Preview、mcai-p0-20261106-d及mcai_p0_epoch_20261106d；缺字段/额外字段、Production、旧c、错误项目/数据库均零读取拒绝。**这只是调用者声明的范围约束，不是缓存后端身份认证**。具有set/delete/expire/clear等能力的接口在读取前拒绝。

固定58键，全加d epoch前缀，仅两遍、无重试：13个canonical物理分片覆盖14来源（tjfch/tjfch_test共享实际分片）；CCGP事件、committed/staging/watch；runtime meta、deep owner、incremental owner/chain、source health原始时钟；SOURCE_POLICIES声明的9来源ledger/bucket/pending/barrier。ccgp增量键可能不存在，读取计划不代表已初始化；区域未实现的增量状态和非CCGP事件存储明确列为未覆盖。

每次get后立即JSON编码并脱离可变引用，比较两遍逐键SHA。canonical、owner/meta、时钟、pending等任何观察到的变化、任意读取失败或超限均整份拒绝，无部分清单。复用既有canonical/事件校验器，检查区域市场和跨分片重复身份；pending barrier采用生产者实际的字符串列表。标记publish的committed优先级，同时保留原始分片，不合并或覆盖。

None保持`UNINITIALIZED_OR_UNAVAILABLE`，缓存未初始化与驱逐无法区分；显式[]保持`PRESENT_EMPTY`。不读取公开latest/published快照、仓库文件、旧c或Production来填充缺失值。不默认生成成功扫描时钟。未知canonical扩展给出JSON路径，辅助对象整体标为语义未覆盖，原值只作为不透明观察保留。

上限可缩小不可放大：单值4MB，两遍累计16MB，canonical/pending/committed/staging记录副本合计10000，单值500000节点、32层。超限拒绝、不截断；固定116次get。本地内核没有为任意注入函数提供抢占式超时，未来真实适配器仍须处理调用截止时间。

## 完整性界限

`status=OBSERVED_STABLE`与`read_plan_complete=true`只表示限定计划读取完成且两遍哈希相等。**现有生产者没有统一原子revision/fence**；双遍读取无法排除ABA、跨键撕裂、读取结束后的写入或稳定缺失。coverage.complete、atomic_snapshot_guaranteed、migration_usable、apply_allowed始终false。元数据、事件关系、pending/barrier关系、未知嵌套值及后端scope证明尚未完成语义覆盖，不能据此声称足以迁移、真实CAS、真实导出或回滚完成。

## 验证与证据

- 新增23项行为测试；标准命令在web/pipeline目录执行`python -m unittest discover -s tests`，**1007/1007通过**。最初仓库根目录的非标准命令有1个包路径导入错误，改用项目prebuild规定目录后通过，未改环境变量或测试代码掩盖错误。
- 冻结官方/衍生模板10/10、原bootstrap CLI正反例3/3通过；既有CLI复现隔离event-watch为空，因此3/3不替代完整事件语义验收。上一轮冻结内存模拟验证器仍通过，生成器、change_id及请求锁不变。
- 覆盖正常、未初始化、显式空、缺标识、跨范围、owner/meta/canonical/health/barrier并发变化、可变引用、两遍部分失败、大小/记录/深度/节点上限、未知字段、实际键格式、无客户端构造和网络调用。
- [离线验证器](validation/ccgp-readonly-export-2026-11-06/verify.py)阻断网络和RuntimeCache构造重建桩。两条河北/吉林记录来自冻结仓库；缓存存在性、空状态、owner和健康时钟是**显式合成外壳，不是云端导出**。证据仅存摘要、逐键SHA和读取轨迹，不重复存原始记录。
- 正常封套SHA：`a3b86c23c2e74601cbbd7e70fff407a73a3aa0162423da1d9c12a4eaa344218b`；未初始化封套SHA：`08b0e23e2a234738df81cac084953af903828fe2e12d7d9abb575a6be7892376`。正常重复输出完全一致，桩输入不变。
- 起点提交下285份原始data、fixtures、既有validation文件字节不变，清单SHA：`2d7fa2d7a5cebffb2c4e53e1085653f3af4d494875650aa754ad57a6de01827c`。见[证据清单](validation/ccgp-readonly-export-2026-11-06/manifest.json)。

未修改运行采集代码、解析器、dry-run或模拟器；未构建/部署、采集、调用项目模型，未修改环境、计划、变量、凭据或权限；未写数据库、运行缓存、原始历史数据或公开快照。未做新浏览器/线上健康检查，来源82cc43f/应用795ef5e只保留历史绑定。提交仅本地，未推送。

下一轮见[next-task.md](next-task.md)：离线审查最小真实只读接入方案、身份/一致性阻断项和单次验收预算，不连接云端、不另建重复dry-run/模拟引擎。真实scope证明、数据读取、原子一致性与迁移均未完成。当前界面无法生成该按钮；提供完整可复制提示词。推荐GPT-6.1 Sol高（high），实际运行模型/思考等级未核实。
