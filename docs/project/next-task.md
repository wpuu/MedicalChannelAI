# 唯一下一任务：A06 CCGP有界原文的候选资格条目分段（需另行授权）

**A05已完成，不重做。** 用户2026-11-08T04:04:50Z批准了2个Python文件的小切片：`web/pipeline/medical_channel_pipeline/ccgp_detail.py`新增`extract_ccgp_qualification_section(text)`纯离线辅助函数；`web/pipeline/tests/test_ccgp_detail.py`增加`CcgpQualificationSectionTests` 11项定向方法。现有Python 3.13标准库**以内存执行11/11通过**，代码片段的UTF-16 FNV、字符数与GitHub新blob中的函数及测试类完全一致。原项目工作树不在当前容器，故**未直接导入运行完整test_ccgp_detail.py**，未重跑旧测试，没安装依赖或新建环境。其他环境未提交修改/在途状态UNKNOWN。

A05返回`EXTRACTED`**只是原文边界安全截取**，从不意味着已验证真实资格；任何状态`requirements_complete=false`、`qualification_verified=false`。对“略／详见附件”、资格标题或结束边界缺失、重复标题、多包件归属不明等返回`INCOMPLETE`；不将辅助函数接入正式parse/canonical/公开快照。

**A06唯一候选，尚未获授权**：仅在同两文件中，给已有A05`EXTRACTED`有界原文新增**离线候选资格条目分句**，按真实文本中明确的“1./2./3.”、“（1）（2）”或可验证的小标题顺序保留原文与相对于原文的行/字符定位；对A05`INCOMPLETE`和不能可靠分句的输入标`INCOMPLETE`，**所有输出一律`UNVERIFIED_CANDIDATE`**，不自动推断硬资格、厂家授权或SATISFIED。这个切片不是官方附件校验、跨包件资格认定或B3验收，真实公告和客户证书仍不读。

**拟严格2文件边界：**
1. `web/pipeline/medical_channel_pipeline/ccgp_detail.py`：只新增离线候选小节分句与原始定位助手，复用A05现有函数；正式公告解析、`_build_verified_record`、`validate_record`等保持不变。
2. `web/pipeline/tests/test_ccgp_detail.py`：只增加A06定向合成正/负/未知、多条款、重复编号、标题污染、包件模糊和无附件回退用例。只运行本轮新增定向测试，不重跑无关套件。

**实施前须用户单独明确批准A06两文件。** 如需改任何额外业务/配置/测试路径，立即停止扩范围并报告。不开PR、不合并main、不安装依赖或创建环境，不上线、部署、不联网官方采集/模型、无云端/真实数据库/客户资料操作。若有真实增量，更新必要交接文件并`[skip ci]`非强推快进提交当前GitHub分支，独立回查HEAD。

产品三项范围仍已批准：天津检验设备经销/代理销售用户；天津血细胞分析仪整机，排除试剂/质控/耗材/维保；可信官方更新→匹配/资格→私有跟进。3家真实客户试用仍未招募。A04详情页对当前无完整资格证据的商机始终`UNKNOWN`。B1–B6全`NOT_VERIFIED`，d Preview`NO_GO_PAUSED`、SDK强保证`CLOSED_NO_GO`、`production_ready=false`、`apply_allowed=false`、`migration_usable=false`。

**推荐 GPT-6.1 Sol / High**，实际设置未核实。

## 完整可复制任务提示词（仅在A06独立授权后适用）

```text
我单独授权MedicalChannelAI A06仅两个Python文件的离线候选资格条目分段，不授权正式线上提取或判断。

以wpuu/MedicalChannelAI的codex/p0-reliability-contracts远端最新HEAD为准，按docs/project/HANDOFF.md、working-protocol.md、current-state.md、checkpoint.json、next-task.md、product-mvp-one-page-2026-11-07.md及qualification-tristate-evidence-contract-2026-11-08.md接手。先看原工作树未提交及在途任务，不覆盖；A05已有extract_ccgp_qualification_section且11项离线方法已以原片段内存验证。

只允许修改web/pipeline/medical_channel_pipeline/ccgp_detail.py和web/pipeline/tests/test_ccgp_detail.py。复用A05有界资格原文，只对确实明确编号的原文段落做确定性候选条目分句和精确原文偏移/行定位，全部标记UNVERIFIED_CANDIDATE；无法确定边界、只有略/附件引用、同公告多包件归属不明返回INCOMPLETE。不得补造硬资格、授权要求和客户资料，不接正式parse、canonical、public_snapshot、资格判断API或AI。只运行新增合成定向测试，不安装依赖、新建环境或重跑未变全套。若二文件边界不够则停止报告并等待另授权。

不部署、不触发采集/模型/Workflow、不访问云端或真实运行/客户资料、不修改数据库、Profile、页面、配置、权限、计划或域名。B1–B6继续NOT_VERIFIED，d Preview NO-GO，SDK/强保证CLOSED NO-GO，apply_allowed=false、migration_usable=false，三客户试用未招募。真实变更加[skip ci]非强推快进GitHub原分支并回查远端HEAD，不建PR、不合并main；结尾分别报告完成、实际测试、未完成与唯一下一任务。推荐GPT-6.1 Sol High，实际设置未核实。
```
