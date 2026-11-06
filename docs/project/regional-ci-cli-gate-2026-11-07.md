# 区域CI补齐CLI离线门禁

2026-11-07（Asia/Shanghai）。起点8b3eba8，分支codex/p0-reliability-contracts、工作树干净，仅根代理，无相关在途工作。开始2026-11-06T18:17:00Z，前台截止18:37:00Z。按最新授权读取协议/状态/checkpoint/next-task及F1/F2/F3报告，只修改既有workflow的paths与unittest清单。

workflow提交`6d4eb1bd48d69329c0a0b3ac4587adcbc1d1e641`，应用仍为58e7e6b。SDK保持CLOSED NO-GO，apply_allowed=false、migration_usable=false。

## 实际变更

修复前两项均缺失，现恰好新增两行：

- [paths:29](../../.github/workflows/regional-medical-refresh.yml#L29)增加`web/pipeline/tests/test_regional_cli_completeness.py`。
- [unittest:63](../../.github/workflows/regional-medical-refresh.yml#L63)增加`tests.test_regional_cli_completeness`，保留原7个模块及原顺序，沿用现有job和set-e。

schedule、push分支条件、concurrency、permissions、job/step timeout、采集/发布/预热步骤及凭据引用全部保持原字节；没有新增workflow/job/环境。没有应用、测试源码、依赖锁或fixture变更。

## 验证

用现有PyYAML BaseLoader解析原/新workflow，不重新序列化文件。删除两条新增行后与8b3eba8原文件字节完全一致；移除新增path并还原原测试run后，整个YAML结构相等，set-e保留。由实际run字段提取`python3 -m unittest`的8个模块后，仅执行该模块组合。

**本地94项测试通过，0失败、0错误、0跳过，耗时3.745秒；其中CLI模块48项。** socket.connect/getaddrinfo及真实vercel SDK导入由审计钩子阻断；未执行workflow中的其他shell命令，测试运行输入/records/report只在现有临时目录测试桩中。运行输出先写系统临时目录，再作为新增本地验收artifact保存。

441份8b3eba8已有data/fixture/历史验收文件逐一SHA256不变；旧验收日志仅做字节哈希，不解析运行日志。1079项Python及冻结10/3仍绑定58e7e6b历史通过结果，本轮按最新指令未重跑。没有用这94项冒充全套、GitHub runner或真实来源验收。

[YAML与命令结构](validation/regional-ci-cli-gate-2026-11-07/workflow-structure.json)、[实际测试结果](validation/regional-ci-cli-gate-2026-11-07/test-results.json)、[新增验收输出](validation/regional-ci-cli-gate-2026-11-07/selected-tests.log)、[证据索引](validation/regional-ci-cli-gate-2026-11-07/manifest.json)。保存的run-selected-tests.py只提取并运行本地离线测试组合，输出到/tmp，不执行workflow其他步骤，不是新workflow或模拟引擎。

## 权限与未完成

没有联网、真实SDK安装/导入/执行、凭据/环境值/运行日志查询、云端/业务/缓存/数据库/函数/Queue/模型调用。没有新环境/路由、计划/变量/权限变更、部署/推送、workflow触发或运行数据/原始历史数据/公开快照写入。

本轮只完成本地CI配置接入与对应模块组合验证。远端工作流执行、Preview部署、真实来源恢复仍未实施；900秒硬退出、同步I/O取消、runtime F2及跨进程共享冷却/Retry-After也未解决。

下一轮回到未完成的runtime F2，仅离线读取阶段执行/Queue/pending/健康更新链，形成一个阶段预算合同和唯一最小方案，不先改runtime或执行函数，不重复CLI修复/SDK审计/条件未变的测试。详见[next-task.md](next-task.md)。当前界面无法生成该按钮；下一轮推荐GPT-6.1 Sol xhigh（超高），涉及阶段租约、pending和重试边界；实际设置未核实。
