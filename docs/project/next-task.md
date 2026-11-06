# 下一轮：补齐可回放的产品纠错 dry-run 变更清单

推荐模型：GPT-6.1 Sol；思考等级：高（high）。实际运行模型/思考等级：未核实。

完整任务提示词：

继续MedicalChannelAI项目。先读取用户最新指令、现有工作树 `/workspace/MedicalChannelAI-p0` 与分支 `codex/p0-reliability-contracts` 的真实最新HEAD和未提交改动、`docs/project/working-protocol.md`、`docs/project/current-state.md`、`docs/project/checkpoint.json`、`docs/project/ccgp-preview-readback-2026-11-06.md`、`docs/project/ccgp-template-audit-backfill-plan-2026-11-06.md`，并检查在途工作。

已部署来源提交82cc43f、应用修复795ef5e，新Preview部署ID `dpl_8Jhc4imHEd6ndBUoth5xBVTrAyL1`。现有项目、d周期 `mcai-p0-20261106-d` 和d数据库不变。本轮已完成部署及只读验收：数据库16条未变，页面15条是报名已结束的1条调研按真实时钟退出，不能重新当作漏显bug。不要重复修复四类已验证问题、部署同一代码、拉取同一批官方原文或触发Queue。

本轮增量工作：复用 `web/pipeline/scripts/audit_ccgp_product_backfill.py`、其安全测试及冻结官方语料，补齐“最多5条、显式选择ID、只读输入”的可回放dry-run变更清单。先审阅已有2条差异提案与既有代码，避免重写第二套审查引擎。补足产品字段对应的官方证据更新、before/after及字段白名单、原记录哈希、官方原文哈希、解析器版本、候选哈希和来源/环境标识；校验身份、市场、项目号、URL和原始版本，拒绝冲突、重复身份、错误环境标识及被篡改输入。保留不相关facts、原始时间、来源成功/扫描时钟和事件，不把历史项目变成新机会；不足5条不凑数、不造数据。

验收标准：冻结模板10/10和原CLI复现3/3继续通过；河北4套扫描仪、吉林5台/套两条提案能从冻结仓库输入重放，证据可定位，所有非白名单字段及输入文件字节不变，重复生成内容/幂等身份一致；错误身份、哈希、环境或超5条明确拒绝。增加必要的行为测试并运行相应回归。输出必须标明 `apply_allowed=false`、使用的是仓库冻结历史输入、并非当前云端canonical导出或迁移完成。

权限边界：仅在现有隔离分支修改代码、测试与文档，进行本地离线dry-run；不新建环境/数据库/角色，不改定时计划、环境变量或权限，不部署、不发模型请求、不触发采集，不写数据库、Runtime Cache、原始历史JSON或公开快照，不切换旧c库或Production。实际canonical导出、原子提交/CAS、迁移、回滚执行和小批云端写入仍需后续独立实现与验收。本轮前台默认最多20分钟，到期报告已有结果和剩余项。

结束时更新当前状态、checkpoint、本文件和证据，报告实际完成/验证/未完成。若没有真正的底部提示词提交按钮接口，明确说“当前界面无法生成该按钮”，提供完整可复制的下一轮提示词；不要使用问答弹窗或链接冒充按钮。下一步注明模型/等级建议及实际设置“未核实”。
