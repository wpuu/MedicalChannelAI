# 下一轮：仅按用户产品意见修订／定案一页方案

本轮产品稿已完成；建议天津、血细胞分析仪单产品线和少量客户，尚未批准。不要重复工程收口，也不要把产品意见当部署或采集授权。真实Preview验收暂停、SDK及强保证CLOSED NO-GO保持。推荐GPT-6.1 Sol high，实际设置未核实。

完整可复制提示词：

```text
继续 MedicalChannelAI，按我本条消息的产品审核意见修订一页方案，仅改文档。

先从GitHub仓库 https://github.com/wpuu/MedicalChannelAI 的 codex/p0-reliability-contracts 分支读取最新HEAD及 docs/project/HANDOFF.md、working-protocol.md、current-state.md、checkpoint.json、next-task.md、product-mvp-one-page-2026-11-07.md，并核对本地/workspace/MedicalChannelAI-p0（若存在）的未提交改动与在途工作。以最新文件和本条用户意见为准，不依赖旧聊天。应用3f88ff7、1213/10/3为已有结果，不重跑测试或重做工程审查。

逐项处理目标用户、首期地区/具体产品线、刷新与后台采集分工、商机判断规则、跟进流程和6项可用版验收。明确已同意、待决定及修改理由；无明确同意时不能把建议写成已批准。若本条未附审核意见，保留待审，不重复造报告。通过标准须能用真实公告更新、发布前后内容和账号跟进持久性核实，不能以测试数量或页面200代替业务通过。

本轮只更新方案及必要状态文档，不修改应用、域名、依赖、workflow、定时计划、变量、权限或保护，仅允许为项目交接访问GitHub，不读凭据/实际环境值/运行日志；不部署、不触发采集/模型或真实缓存/数据库/Queue。获授权的文档成果应正常提交并快进同步当前GitHub隔离分支，遵守工作约定第9条，推送后核对远端HEAD；不强推、不合并main、不创建PR或触发workflow。真实验收仍暂停，apply_allowed、migration_usable=false。产品范围定案不自动授权代码或云端动作；不重开SDK/强保证或追加模拟层，前台20分钟。

结束时展示修订后可直接审核的方案、实际变更和仍待决定事项。当前界面无真正提示词发送按钮时明确说明并提供完整提示词。推荐GPT-6.1 Sol high，实际设置未核实。
```

交接归档入口：docs/project/HANDOFF.md。已获授权的GitHub归档不等于部署；产品建议仍待用户审核。
