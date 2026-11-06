# 整批前置校验与内存回滚模拟

2026-11-06（北京时间）。本轮增加独立薄层 `simulate_ccgp_product_corrections.py`，代码 `8f8b5cc50e77087197f05b70b7fb2fee3857b57d`。复用既有生成器、请求锁、变更清单和canonical校验器，不改变9f6生成器及已有change_id规则。**984项Python、冻结模板10/10、原CLI3/3通过**；两条候选可在内存中整批overlay并精确恢复892条原状态，重复投递为零修改。没有真实提交、CAS、迁移或回滚。

## 起点和范围

开始时HEAD为8e46a86，工作树干净；读取用户最新指令、工作约定、当前状态、checkpoint、next-task与上一轮dry-run报告。只有根代理运行，无其他代理或附着终端任务。使用现有工作树/分支，未访问云端、读取凭据、创建环境、修改定时计划/权限、部署、触发采集或项目模型。

输入仍为仓库两份892条历史canonical文件、原官方/衍生fixture、请求锁和上一轮冻结change-set。为模拟构造的内存外壳包含scope引用、records以及空events/pending；空外壳是演练输入，**不表示云端没有事件或pending**。并发事件/事实负例是明确的测试注入，不是真实公告新增产物。

## 校验与幂等语义

1. **独立重建可信清单**：调用既有build_dry_run，核对请求SHA、预期项目/d周期/数据库、原文/基线/解析器版本和官方字段证据；传入清单必须与重新生成结果完整一致。即使篡改者同时重算候选、change_id和batch ID，未验证的证据仍被拒绝。
2. **整批前置检查**：校验完整内存外壳的scope/种类和调用者给出的expected_state_sha256，使用现有canonical校验器检查892条身份/重复项目；所选条目必须全部处于准确before版本或全部处于准确after版本。任何一条缺失、冲突或混合状态都整批拒绝，不修改调用者对象或半数副本。
3. **内存overlay**：全部before且检查完成后，才建立副本并放入2条已验证候选。890条未选择记录及events/pending等其他内容保持一致。前置检查后和返回前再次核对原状态指纹，负例覆盖检查后出现的新事件。副本不写回文件、缓存或数据库。
4. **重复投递**：全部after且调用者显式提供当前状态版本时，返回ALREADY_SIMULATED，changed_record_count=0，不生成新的应用回执。混合before/after不被当作可继续完成的部分批次。
5. **回滚回执**：首次模拟返回绑定清单ID、scope、所选ID、完整before/after状态哈希的内存回执。回滚额外要求调用者独立给出回执canonical SHA；核对回执内容/身份及完整当前after版本，再恢复允许产品字段和对应旧证据。非白名单内容不变，结果须精确等于原状态哈希。
6. **回滚幂等及并发拒绝**：准确原before状态再次回滚返回ALREADY_RESTORED、修改0条。出现新事实、新事件或pending（即使不在所选记录）会因完整状态版本不一致而拒绝，保留新数据；这是保守的整状态拒绝策略，不是合并后续变更的算法。

两次CLI报告字节完全相同，内部四阶段结果：

| 阶段 | 状态 | 修改条数 |
|---|---|---:|
| 内存overlay | SIMULATED_APPLIED | 2 |
| 重复overlay | ALREADY_SIMULATED | 0 |
| 内存恢复 | SIMULATED_RESTORED | 2 |
| 重复恢复 | ALREADY_RESTORED | 0 |

原状态SHA `7d8bb50314f7641b8cd73021b8c5c52bc2879cfd00ef90868b7ee0018a517522`，overlay后 `5bcaf1fbd9d5940d2af0cd2e860015c752e615c50defb86496ba3d0d90fda8ef`，恢复后精确回到原SHA。旧变更清单ID仍 `5bb62880aa451309cd8f86eb029354ca7bc9709ba0d628ca108f25cc24c59420`。

## 验收与文件保护

18项新增行为测试，完整Python为966＋18＝984，通过。覆盖错误before/after哈希、自洽重算哈希的伪证据、跨环境、第二条无效而第一条有效、缺失记录、混合状态、提交前及前置检查后并发、回滚时新增事实/事件/pending、回执篡改/错批、完整幂等、网络阻断及CLI失败不覆盖既有报告。旧10/10和3/3复现保持通过。

独立CLI两次完成往返，核心在阻断socket/urlopen时也完成同一演练；所有原始基线、请求、fixture、已有生成器及清单字节未改变。CLI只写哈希/状态摘要，不导出892条新的canonical文件。输出仅允许系统临时目录，或仓库docs/project/validation下新增artifact；原输入、软硬链接、源码、公开快照及已存在的仓库证据均拒绝覆盖。报告落盘原子替换不等于运行数据事务。

完整内存状态文件仅在/tmp作本地验收输入；仓库证据保留可重建外壳配方、报告、输入哈希和最终日志，避免重复提交整份892条数据。可运行[离线验证器](validation/ccgp-memory-simulation-2026-11-06/verify.py)重建并复核四阶段。

## 实际限制与后续

模拟中的版本检查只是对Python对象的检查与深拷贝。它没有实现跨进程锁、原子比较交换、数据库事务或分布式租约；不能保证检查返回后真实写入器不会改变状态。回执/状态SHA是调用者独立信任的版本锚，不是数字签名或授权凭据。所有报告始终apply_allowed=false、runtime_cas_implemented=false，未实施真实应用、真实回滚、canonical导出、迁移或快照发布。

解析器、bootstrap、API/前端、部署配置、原始历史数据和已冻结证据未改；未跑新的JS构建或浏览器验收。本轮未访问Preview/Production，不把旧云端记录当新检查。来源82cc43f/应用795ef5e的部署绑定沿用历史，production_ready=false。

下一步见[next-task.md](next-task.md)：先在本地实现现有d命名空间的canonical只读导出内核与完整性校验，不新增HTTP路由、不部署、不调用云端、不切换旧c或Production；真实导出仍待后续授权步骤。这样补齐当前缺少的运行状态输入契约，再讨论真实提交机制。

本轮北京时间20:26:01开始，前台截止20:46:01。证据见[冻结清单](validation/ccgp-memory-simulation-2026-11-06/manifest.json)。当前界面无法生成真正的底部提示词按钮，给完整可复制任务；推荐GPT-6.1 Sol高（high），实际运行模型/思考等级未核实。
