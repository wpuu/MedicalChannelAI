# MCAI-HERMES-JOINT-REVIEW-20260925

> **SUPERSEDED NOTICE — 2026-09-25**
>
> 本文原始联合审计结论保留作历史记录，但其中 **Hermes Sample Gate H0 的“先取得真实客户资料/已结束项目资料再允许 75126”前置条件，以及“先做老杨真实资料员流程采样”的当前优先顺序，已被同日后续 Owner 决策 supersede。**
>
> 当前权威修正见：
> `docs/reviews/MCAI-ZERO-TRUST-OWNER-DECISION-20260925.md`
>
> 75126 仍为 DEFERRED，但原因已改为“尚未出现经过 A 侧价值之后的真实 L3 私有核验需求/明确受控演示触发”，不再以客户先交整套真实资料作为硬前置。

日期：2026-09-25  
性质：GPT-6 Sol 联合产品 / 架构 / 商业终审的 Owner 接受记录  
结论：CHANGE；有条件保留协同假设；当前联合商业闭环 NOT PROVEN。

## Owner 接受的核心决策

1. MedicalChannelAI：KEEP，但收窄并验证。保留官方来源、事实版本、公共共享采集、公共 AI 缓存与私有 overlay；不以历史记录总量宣称覆盖率或客户价值。
2. Medical Channel Hermes V0：KEEP Stage 1；后续开发必须经过真实客户/样本 Gate。资料篮不是正文解析、Product Identity Graph、缺件/冲突复核或可交付资料包。
3. 两项目：代码、仓库、公共/私有数据面保持独立。先人工并排验证；只有真实价值 Gate 通过后，才考虑版本化的窄 PublicOpportunity 契约。
4. 不把 B 的原始注册证、授权、报价、联系人或工作区路径直接送入 A 当前 AI customer_context 路径。
5. 不宣称自动投标、有效授权保证、全自动资料包或已形成商业闭环。

## PR #23

PR #23 已于 2026-09-25 关闭，未合并。

原因：
- 与既有 Vercel Incremental Collector / Queue / Tick 重复形成第二套调度；
- 破坏既有 Tianjin/Regional deep-refresh concurrency contract；
- 已知 URL 的白天变更/终止没有被 incremental-only 复核；
- snapshot canonical / 发布单写者仍未统一；
- 在商业验证前引入高频整省 GitHub Actions 扫描增加维护与源站压力。

可复用思路：bounded lookback、NEW/CHANGED 优先、无变化不发布。后续只在现有 Incremental Collector 内，从一个有真实客户价值的 Regional source 做窄适配。

## Gate 分层，禁止同名混淆

### Hermes Sample Gate H0
仅决定是否允许派发 75126 这一低悔解析基础设施：
- >=1 套经授权的已结束项目资料；
- 至少一次真实资料操作者流程走查；
- 完成格式普查；
- Codex capacity 可用；
- 派发前重新核对 HEAD/TREE，并按 PROTOCOL 创建和回读 coordination card + reservation。

14 天到期只触发 Owner 重新评估，不是自动 PASS。

### Joint Business Gate A
控制 Stage 2B/3 扩张、A↔B 联通和更大商业投入：
- 至少 2 家互不关联企业；
- 每家至少 5 个真实机会/获准资料任务的受控对照；
- 至少 1 家实际支付有范围/金额/交付约定的验证费用；
- 第二家有可核验的预算审批动作；
- 总工时/错误指标有真实对照；
- 无未经授权的私有数据外发；
- 不允许用口头“有兴趣”替代。

## 当前优先顺序

1. 老杨公司真实资料员流程采样；
2. 获取授权的已结束项目资料与格式普查；
3. 同题比较当前工作流 / 通用 AI + 合理模板 / 现有标讯或审标工具；
4. 记录真实耗时、错误、补件、复用比例；
5. 75126 继续 DEFERRED；
6. 不启动 A↔B API/Skill，不合并仓库；
7. MedicalChannelAI 的下一次 Regional 增量工程必须沿用现有 Incremental Collector，而不是新建第二套 scheduler。

## 停止条件

若真实客户资料基本由厂家代做、月均任务很低、现有工具已覆盖、通用 AI + 模板同样好用、或每单仍需大量创始人人工处理，则停止把该协同方向扩张为 SaaS，不因既有开发量继续投入。
