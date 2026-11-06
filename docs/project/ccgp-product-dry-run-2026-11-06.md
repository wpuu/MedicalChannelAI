# 产品纠错 dry-run 变更清单

2026-11-06（北京时间）。本轮复用现有 `audit_ccgp_product_backfill.py`，增加锁定请求、显式选择及字段证据完整的离线dry-run模式，代码 `9f6ac310fee4b0c68e92a6233e23bdc03cfa9ce3`。已有两条提案已生成可回放清单；**966项Python、冻结模板10/10、原CLI复现3/3通过**。没有部署、访问云端canonical、调用项目模型或写任何线上数据。

## 起点与增量

开始时HEAD/远端均为c25ff26，工作树干净，main仍3216fd9；读取了最新用户指令、工作约定、next-task、当前状态、checkpoint和上轮Preview报告。只有根代理运行，无其他代理或附着终端工作。现有部署来源82cc43f、应用795ef5e及15/15页面解释保留历史绑定，本轮没有重复部署或查线上页面。

原审查入口、10份冻结语料和解析器保持不变。新增模式共用同一次审查/解析结果，不另造抓取器或第二套审查引擎；普通 `audit()` 结果和原CLI保持兼容。

## 清单内容与拒绝边界

- 输入标记为 `FROZEN_REPOSITORY_CANONICAL`，基线仍是仓库892条历史记录，**不是云端canonical导出或迁移完成**。目标d周期/数据库/项目只作引用标识，工具不读取环境变量或连接它们。
- [锁定请求](../../web/pipeline/tests/fixtures/ccgp_product_dry_run_request_20261106.json)显式列出2个机会ID、市场/项目号/来源ID/URL、原记录哈希、官方原文字节哈希、解析器文件哈希、fixture manifest哈希及全部基线文件字节哈希。独立CLI参数必须再次给出请求SHA和预期项目/周期/数据库；不从请求自己推导可信目标。
- 强制选择1–5条；不自动填满5条。重复ID、别名同项目、非官方衍生样本、无提案ID、身份或市场冲突、旧版本/篡改输入、错误环境和超量均拒绝；语料门禁失败或为空也不生成清单。
- 只允许 `facts.product_items`、`facts.product_categories` 和这两条字段路径对应的证据行变化。候选记录合入解析器产生的官方URL/locator；分类清空时删除旧分类证据，保留其他证据的内容与顺序。候选经现有canonical校验器复核，所有非白名单字段保持一致。
- 输出包含before/after、完整candidate_record及其哈希、官方定位和获取时间、解析器/清单生成器文件哈希、逐条change_id和batch change_set_id。原source.observed_at、报名/投标/发布日期、市场身份及其他记录字段不变；没有重算快照、排名或刷新成功时钟。
- 输出始终 `apply_allowed=false`，同时 `runtime_canonical_exported=false`、`migration_complete=false`、`network_requests=0`。即使门禁全绿也不提供apply开关。
- 输出不得覆盖请求、基线、fixture或指向它们的软/硬链接，也不能落在受保护原始数据/源码目录内。仅将完整报告原子替换到指定本地artifact路径，避免硬链接写穿到未选择输入。这只是报告文件的安全写法，不是运行数据库的事务/CAS实现。

两条真实候选：

| 机会ID | 产品修正 | 对应字段证据 |
|---|---|---|
| ccgp_he_2a9ca892bf9d0b6a | 空列表→病理数字化切片扫描仪4套 | 官方采购需求/正文结构化产品明细 |
| ccgp_jl_806743d8af167ea4 | 空列表→血液透析机5台/套 | 官方采购需求/结构化采购表标的名称与数量 |

原有项目已经处于历史时间范围。输出保留其真实日期和原始事实阶段，没有生成新的行动快照，不能把它们当今天的新机会。

## 验证结果

21项新增行为测试涵盖显式单选/空选/超5条、重复及别名身份、错误市场/项目/来源/URL、请求/基线/manifest/官方原文/解析器版本、环境绑定、证据替换、输出覆盖/软硬链接和失败时保留既有报告。全部Python为945＋21＝966，通过。

两次独立CLI输出字节完全相同，逐条change_id和批次ID一致。对核心生成函数阻断socket及urlopen后，输出与CLI完全相同；请求、892条基线文件、manifest和全部官方/衍生fixture输入字节均未改变。批次ID为 `5bb62880aa451309cd8f86eb029354ca7bc9709ba0d628ca108f25cc24c59420`。

模板10/10和原CLI3/3重新通过；应用解析器、bootstrap、API、前端、部署配置均未修改。本轮只改离线工具/请求fixture/测试，未重复JS构建或浏览器验收，不把上轮945完整构建说成本轮966完整构建。

开发中补充测试曾因字典键拼写错误未能加载，已修正；最终966项测试全部实际加载并通过，以冻结最终日志为准。

可在仓库根目录复现（只写指定/tmp报告）：

```bash
python web/pipeline/scripts/audit_ccgp_product_backfill.py \
  --manifest web/pipeline/tests/fixtures/ccgp_template_audit_20261106/manifest.json \
  --baseline web/pipeline/data/tianjin_live_ccgp_records.json \
  --baseline web/pipeline/data/regional_live_ccgp_records.json \
  --dry-run-request web/pipeline/tests/fixtures/ccgp_product_dry_run_request_20261106.json \
  --expected-request-sha256 9c4533103fc04b795a9a8f9f70006e836ac5fe49c7dac5648c58d8907f7c6aea \
  --expected-project-id prj_7fk44eKUhdbfTUaXxEBMgIzZiqUM \
  --expected-preview-epoch mcai-p0-20261106-d \
  --expected-database mcai_p0_epoch_20261106d \
  --output /tmp/ccgp-product-change-set.json
```

上述“锁定”是对调用者独立信任的请求SHA和预期范围做一致性检查，不是数字签名或人类批准记录；若同时改请求和信任锚，须重新审阅。scope只是离线引用，不能证明这些文件就是该环境的实时数据，更不授予环境访问或写入权限。

## 未完成与权限边界

没有新建环境/数据库/角色，没有修改定时计划、环境变量或权限，没有触发采集或项目模型，没有写Runtime Cache、原始历史JSON、公开快照或数据库；Git仅同步当前隔离分支。Production和Preview本轮均未访问或复核，不能用上轮只读记录冒充新检查，`production_ready=false`。

真实canonical导出、提交前运行版本检查、原子提交/CAS、迁移、回滚执行及小批云端应用仍未实现。本轮提案只用于审阅，不能直接送进旧写入器。下一步应先复用本清单完成**内存中的整批前置版本检查和回滚模拟**，用并发变化负例验证全拒绝而非部分修改；不把模拟结果说成真实CAS或上线准入。

完整后续任务见[next-task.md](next-task.md)，本轮证据见[冻结清单](validation/ccgp-product-dry-run-2026-11-06/manifest.json)。本轮19:56:02开始，前台截止20:16:02，完成后不继续等待后台任务。当前界面没有真正的底部提示词按钮接口，提供完整可复制提示词；普通工程推荐GPT-6.1 Sol高（high），实际运行模型/思考等级未核实。
