# 下一轮：暂停；仅收到完整新证据及明确分项授权后一次复核

当前真实d Preview验收NO-GO。应用3f88ff7、本地1213/10/3与R1离线关闭保持。缺口已一次列清，不安排重复收口、部分元数据试探、部署、试跑、SDK审计或模拟补证。没有可自动执行的云端或代码任务；只有“继续”而无新证据时报告保持暂停，不再制造新验收轮次。推荐GPT-6.1 Sol xhigh，实际设置未核实。

以下是条件性完整提示词，提交本身不批准任何云端操作：

```text
继续 MedicalChannelAI，仅在本条消息同时提供完整新增外部证据及逐项明确授权时，一次性复核现有d Preview验收放行；否则保持NO-GO暂停，不重复写相同报告或生成新补证轮次。

先核对 /workspace/MedicalChannelAI-p0 最新HEAD、未提交改动和在途工作。读取用户最新指令及 docs/project/working-protocol.md、current-state.md、checkpoint.json、next-task.md、d-preview-acceptance-decision-2026-11-07.md、ccgp-runtime-access-stop-2026-11-07.md。应用3f88ff7及1213/10/3为已有离线结果，不重跑未变测试或重做R1；拟部署来源固定b710804，若换SHA须重新绑定，历史82cc43f/d部署不是当前状态。

逐项核对决策包G1–G7：可信项目/团队/Preview/d/数据库/权限身份，准确bundle/依赖/构建，消息消费者和旧writer及执行窗口，符合完整性的CCGP执行范围/请求上限，可信canonical/pending/权威读回渠道，GET/build副作用控制，以及元数据、构建、部署、触发、读回、临时材料清理的分别授权。

只有新增证据完整覆盖所有阻断才形成一次具体放行结论；任何缺项保持未核实和NO-GO并结束，不先查一点、先部署或转用tjzyefy冒充CCGP验收，不猜SDK参数/能力，不重开SDK或强保证，不追加模拟层。无新证据时仅简短说明暂停，不改文件、不执行工具补证。

本提示词默认仅现有隔离分支离线文档。没有另行准确批准的操作不得执行；不联网、不读取凭据/实际环境值/运行日志、不调用云端/业务/真实缓存/数据库/函数/Queue或模型，不运行应用/SDK/测试/构建，不部署、不推送、不触发workflow，不新建环境/路由，不改应用、锁、workflow、计划、变量、权限、保护或运行数据，不清pending/owner、不自动回滚。apply_allowed、migration_usable始终false，前台20分钟。

报告新增证据、实际完成与仍缺内容；按钮不可用时明确说明并提供完整条件提示词。推荐GPT-6.1 Sol xhigh，实际设置未核实。
```
