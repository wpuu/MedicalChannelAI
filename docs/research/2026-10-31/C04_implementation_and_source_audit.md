# MED-ACTION-20261031/C04｜更正公告版本审计与采集证据闭环（隔离执行）

研究与验证日期：2026-10-31（北京时间）
基线：fix/c03-ai-clock-official-provenance-20261031 / b756407bd058b69b949c655d47a02da2ee43c077
本轮分支：fix/c04-source-proof-20261031
测试代码提交：90c4832379aeae01cc91b1048fe73e425d5673b8
裁决：C04_ISOLATED_BUILD_PASS / OFFICIAL_LATEST_CORRECTION_UNVERIFIED / REAL_COLLECTOR_NOT_PROVEN / RELEASE_HOLD
绝对边界：没有向生产部署，没有合并main，没有修改PR75/PR78、密钥、Cron、Queue状态、数据库，不联系客户或收费。

## 一、结果摘要

本轮完成了可复现的隔离开发，而不仅是研究计划。

1. 2026-10-30的两条更正公告得到第三方独立索引/转载佐证；但A-939、A-944的正式更正正文与标色DOCX原件均未获取。因此未能给出安全可信的“具体哪个设备/参数/截止日期变化”对照，所有差异留UNKNOWN。
2. 在PR78/C03隔离代码上新增非权威、fail-closed的采集执行证据模块，真正接入Cron已接受的Queue send、有效租约的Queue delivery、stage success/failure和durable snapshot回执。每事件独立缓存键、读回验证、重复消息不抹写证据。
3. 在实际发布函数内，可选地将已核验的上一阶段证据摘要绑定到当前verified snapshot；既有durable publish/base-match/历史保留门禁完全不改。若证据不完整或缓存丢失，跳过证明，不创造“成功”。
4. 为只读collector-status增设源级证据/新鲜度字段，对无证据显示UNKNOWN，不把一个Stage的成功冒充官方数据源覆盖完成。当前实现仅允许已有的已激活五源；PR78三源未激活。
5. CI最终通过：20项C04 proof、37项旧双时段调度、25项旧来源parity、986项Python全量，以及npm run build(含prebuild、966+新增20单测、AI边界、TypeScript、Vite)；独立JS检测确认公开快照允许脱敏的附加witness，并仍拒绝api_key等敏感字段。

## 二、官方公告版本的证据边界

### A939：第五批检验科设备采购

政府采购官方原稿：
https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261027_27573388.htm

2026-10-27版公开正文可以明确：
- 第1包：全自动生殖道分泌物分析仪、血气分析仪，包预算248万元、最高限价227万元；
- 第2包：全自动化学发光免疫分析仪、血液分析仪，预算104.99万元、限价59.99万元；
- 第3包：全自动尿液分析流水线、微生物样本前处理系统，预算95万元、限价80万元；
- 第4包：生化培养箱、二氧化碳温箱，预算和限价均61.2万元；
- 合计509.19万元预算、428.19万元限价；不接受进口产品；“等”说明非完整BOM；
- 原定文件获取结束2026-11-03 16:00、投标结束11-17 09:30，但10月30日有更正索引，现时是否变化UNKNOWN。

2026-10-30第三方目录存在同项目号更正公告标题：
https://m.chinabidding.cn/xdwzb_3/zbbx/

本轮按官方域名严格搜索，未取得正式更正全文/附件；官网原始需求DOCX下载入口
https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=yUJ.S_Ra1oE%2A&method=downEnId
仍返回cache miss；GitHub Actions上一次官方原始HTML GET为HTTP403。没有绕过限制，也没有下载可哈希的完整文件。

因此：
- “有更正线索”＝SECONDARY_INDEX_ONLY；
- “产品/预算/报名/开标是否更改”＝UNKNOWN；
- 不允许以10/27原稿生成10/31仍确定可投的行动卡；
- 不用A944更正结果填A939。

### A944：第四批检验科设备采购

2026-10-27原公告链接：
https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261027_27572316.htm

2026-10-30第三方转载称项目需求书改动，颜色标注见更正附件：
https://www.czhaobiao.com/zb-196981466-3.html

没有获得可哈希的官方更正附件；A944包级产品、技术要求、数量、限价、截止日具体变化均UNKNOWN。不能只从转载的“其余内容不变”就确定全部采购事实版本有效。

两条公告的证据分级、已知原稿与每个未核字段保存在：
docs/research/2026-10-31/C04_official_version_comparison.json

### 错误做法明确禁止

- 不能把“第三方目录标题”升级为“官方更正事实已核实”；
- 不能用旧附件颜色标识的猜测替代真正的变动对照；
- 不能把原公告报名截止日无条件视作最新；
- 不能把C02合成HTML测试视为真实政府采购原始DOM回放；
- 不用外部采购网站的类目、时间、金额覆盖官方已核事实。

## 三、采集证据代码与设计裁决

### 3.1 新增的文件与已修改入口

- web/collector_proof.py：独立审计侧车，不授权发布、不参与排序。
- web/api/collector-run.py：确认真正Queue send成功后才记录TRIGGER_ACCEPTED和STAGE_ENQUEUED；重复idempotency响应不假装首次触发成功。
- web/collector_queue.py：只有消息版本/日期/lease/fencing通过后记录STAGE_DELIVERED；真实run_stage完成后记录STAGE_COMPLETED；失败/终止标记独立；最后publish获得durable acceptance及缓存读回后才写SNAPSHOT_CONFIRMED。
- web/collector_runtime.py：采集既有检查全部通过、durable发布之前，从已记录的源级阶段计算简短witness；只有证据完整才作为collection_coverage.collector_source_witness一起持久化；原有完整性、历史回退和发布时间门禁保留。
- web/api/collector-status.py：加readonly execution_proof，含今日各周期证据、已激活源最近阶段成功时间及UNKNOWN/STALE。status不允许有任何“证据缺失却显示healthy”的捷径。
- web/pipeline/tests/test_collector_proof_c04.py：缓存、重复送达、源失败、无租约拒绝、确认durable receipt、7日时间窗回放、Cron真实send与Queue集成mock。
- web/scripts/check-collector-proof-public-snapshot.mjs：用仓库真实bundled快照做schema验证，允许上述可选字段但拒绝注入api_key。
- .github/workflows/c04-source-proof-validation.yml：隔离CI，不触发deploy。
- web/vercel.json：显式关闭当前C04 branch的自动Vercel Preview。

### 3.2 恰当理解“耐久”

Runtime Cache不是持久审计数据库：这里单事件TTL为21天，表示设置了**期望保留上限**，不等于绝不丢失；服务器区域、重新部署、TTL到期和Cache淘汰均可能令单条证据缺失。缺失永远输出UNKNOWN。

为降低这种风险，在成功durable snapshot中可选嵌入较小的collector_source_witness，这份数据会随已验证的公开JSONB快照走原来的持久化途径。它的本意是证明“此次快照前，经历过哪些有证据的阶段”，而非保证过去7天所有成功/失败皆有不可篡改审计账本。

**仍缺的能力**：
- 失败/被阻断周期的独立长期持久审计（因为那些周期不产生新的verified snapshot）；
- 真实来源页面完整窗口、30日分页、原始HTML哈希和所有详细条目都验证完成的源级证明；
- 旧部署in-flight/delayed Queue真实分区/消费者的状态；
- 经授权发布后的7天自然Cron执行证据。
这些必须保留C05门禁，不准因C04代码测试成功就假称完成。

### 3.3 Fail-closed测试点

- 无真实Queue接受 → 无TRIGGER_ACCEPTED；
- Queue send报错 → 不记成功；
- 无lease或旧周期消息 → 原有代码抛出COLLECTOR_ACTIVE_CYCLE_MISSING，不标STAGE_DELIVERED；
- 失败/终止 → STAGE_TERMINAL_FAILURE，不生成SNAPSHOT_CONFIRMED；
- 无durable receipt → 不生成SNAPSHOT_CONFIRMED；
- 阶段缺证据 → 当前cycle的完整性PROOF_NOT_AVAILABLE；
- 仅SOURCE stage完成且未发布快照 → source freshness UNKNOWN；
- 旧快照、新快照、私有字段与禁用Preview边界不改变；
- 输出仅带阶段名、周期ID、时间、可接受的错误码、SHA/计数，不存token、供应商私有关系、原文URL凭据。

## 四、GitHub Actions真实验收

首版C04 14项模块测试 + 原有37/25项 + 全量980项及完整构建通过：
https://github.com/wpuu/MedicalChannelAI/actions/runs/41091466281

随后增加了6项Queue/Cron源代码集成测试；新增测试曾把“无租约消息”错误假定为静默返回，真实旧代码正确抛出异常要求Queue重试。修正测试预期后，完整20项C04测试和全量986项/构建通过。最后增加独立JS的Public Snapshot安全证据验证，最终完整CI：

https://github.com/wpuu/MedicalChannelAI/actions/runs/41092275503

精确经过测试的提交：90c4832379aeae01cc91b1048fe73e425d5673b8

CI SUCCESS：
- C04定向20项 PASS；
- 旧TwiceDailySearch 37项 PASS；
- 旧TwiceDailySourceParity 25项 PASS；
- Python全量986项 PASS；
- 完整npm run build再次运行986项，AI boundary/prebuild PASS；
- TypeScript PASS；
- Vite build PASS；
- 可选collector source witness正式Public Snapshot schema校验PASS；
- 禁止api_key发布的边界PASS。

这仍只是隔离环境执行与模型数据验证，不是生产Cron、真实Cache和真实Queue的网络端到端部署测试。

## 五、生产只读核验与不确定性

main仍为3216fd940dabfa7714383b6436908f9b72ff8a9c；PR75/PR78都是Draft/open；C04基于C03+PR78隔离候选但未合并。

当前Production保留一条每天08:20北京时间Cron设计（不是PR78计划中的两条）；C04没有改变Production/Cron/Queue、没有新Preview部署。

上一次C02成功读到的公开状态：DATABASE snapshot在2026-10-28T08:27:29.111217+08:00，STALE/degraded，65条机会，collector-status无完整stage/tick/chain记录，pipeline-health HTTP503。

C04内反复尝试最新生产API读取受到工具内部错误限制，未获得一份较10月30日更新、更晚的可靠快照，因此没有声称现在已经恢复。过去30分钟Vercel采集日志查询无记录，但该时段并非天然Cron运行窗口；不代表Cron失败。历史日志受Hobby计划留存限制，不足以回溯真正触发和delivery。

在缺失真实Cron、Queue与发布读回之前，最终发布门禁仍HOLD。连7天真实自然运行的成功证明都没有，不能对客户承诺“稳定每日监控”。

## 六、C04放行决策

**离线代码能力通过**：可追踪一次已授权Cron周期的接受→分阶段Queue执行→已确认持久快照；缺证据不改发布结果，永不把未授权/无租约消息记成功。

**商业发布不通过**：
1. A939/A944最新官方更正与标色附件无法读取；
2. 原始官方HTML未取得可回放文件，C02包表只是合成HTML回归；
3. 生产Cron→Queue→Source→Durable连续7天未验收；
4. 现有PR78 source 30日完整窗口、<=3详情分批、整源提交与25stage正式接线尚未完成；
5. 真实客户付费意愿与Agnes相似相关性基准尚未核实。

下一步C05：
- 寻找合规可读取的官方更正全文、正式原始HTML、两个项目需求DOCX；逐字段原稿/更正版对照；
- 审查正式源窗口/Cursor与Queue原子提交协议，并在隔离分支补独立长寿命错误周期审计（不能把Cache当数据库）；
- 通过绝对文件证据及完整CI后，再申请单次授权的生产发布和7天自然运行验证；
- 失败或官方授权不足则HOLD，不替用户联系医院、买标书或改系统。
