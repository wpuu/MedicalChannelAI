# MedicalChannelAI｜A03 资格三态证据合同与 A04 最小开发授权卡

日期：2026-11-08（北京时间）｜**本轮只有 GitHub 仓库静态检查与文档，无应用开发、测试或线上运行**。仓库 `wpuu/MedicalChannelAI`、分支 `codex/p0-reliability-contracts`、核查基线 HEAD `a85d6c9faa8dab1e6bd63dc7691facb13726f5b7`。

## 1. 首期范围与事实级别

产品范围**已由用户批准**：天津地区医院检验设备经销／代理商的销售负责人及业务人员；仅天津采购单位的**血细胞分析仪整机**，不包括试剂、质控品、耗材、维保和其他检验设备；以真实官方商机更新→可信产品匹配与资格判断→私有跟进提醒为首期价值。页面只读已发布结果，后台采集另由受控任务执行。**3家真实客户试用仍未招募，未获本轮外联/试用许可**。

A01/A02：商机池、Today 卡片、详情已有“整机相关／非本期整机／证据不足待核”**源代码显示层**，仅代表产品类别线索，**不等于型号参数或投标资格**。A01 新 Node 离线34/34是历史记录；A02在GitHub blob做过静态35/35，但`--a02-only` Node目标脚本、TypeScript typecheck、浏览器、实际公告验收**尚未在原项目环境执行**。B1–B6全部`NOT_VERIFIED`。

本轮已查看 GitHub 六份最新交接文件及以下精确源码；原`/workspace/MedicalChannelAI-p0`、`/workspace/MedicalChannelAI`和`/mnt/data/MedicalChannelAI`在当前容器均不存在，故**其他环境工作树未提交改动和在途工作 UNKNOWN**，未克隆或生成替代环境。

## 2. 实际已存在什么，缺什么（不是猜测）

| 领域 | GitHub 原文件证据 | 结论 |
| --- | --- | --- |
| **官方公告资格原文** | [web/pipeline/medical_channel_pipeline/ccgp_detail.py](https://github.com/wpuu/MedicalChannelAI/blob/a85d6c9faa8dab1e6bd63dc7691facb13726f5b7/web/pipeline/medical_channel_pipeline/ccgp_detail.py#L538-L552)的`_procurement_text_ranges`使用“申请人／投标人／供应商资格要求”**作为采购需求文本的结束分界**；[web/pipeline/medical_channel_pipeline/ccgp_detail.py](https://github.com/wpuu/MedicalChannelAI/blob/a85d6c9faa8dab1e6bd63dc7691facb13726f5b7/web/pipeline/medical_channel_pipeline/ccgp_detail.py#L1263-L1328)的`_build_verified_record`仅构造项目、采购单位、产品、预算、期限等字段，未产生`qualification_requirements`和逐条`locator`。 | **解析器会遇到标题，但不是已抽取并核验资格条款**；具体官方附件是否完整、对应包件以及实际条文，本轮未知。 |
| **可公开引用的结构化资格字段** | [web/pipeline/medical_channel_pipeline/validation.py](https://github.com/wpuu/MedicalChannelAI/blob/a85d6c9faa8dab1e6bd63dc7691facb13726f5b7/web/pipeline/medical_channel_pipeline/validation.py#L7-L31)的`CRITICAL_FACT_PATHS`未定义资格字段；[web/pipeline/medical_channel_pipeline/public_snapshot.py](https://github.com/wpuu/MedicalChannelAI/blob/a85d6c9faa8dab1e6bd63dc7691facb13726f5b7/web/pipeline/medical_channel_pipeline/public_snapshot.py#L341-L377)构造公开快照没有资格清单；[web/src/types/public.ts](https://github.com/wpuu/MedicalChannelAI/blob/a85d6c9faa8dab1e6bd63dc7691facb13726f5b7/web/src/types/public.ts#L10-L40)的`PublicFacts`也没有。 | **当前公共快照无逐条资质/授权/型号满足证据**，不能凭现有`VERIFIED`标志推出“投标资格已验证”。该标志只绑定已支持的公开事实字段。 |
| **客户能力与私有资料** | [web/src/services/localCustomerProfile.ts](https://github.com/wpuu/MedicalChannelAI/blob/a85d6c9faa8dab1e6bd63dc7691facb13726f5b7/web/src/services/localCustomerProfile.ts#L11-L46)只有`keyword/capability_type`、医院关系、经营选项；[web/api/profile.js](https://github.com/wpuu/MedicalChannelAI/blob/a85d6c9faa8dab1e6bd63dc7691facb13726f5b7/web/api/profile.js#L86-L151)验证账号资料不接收证书编号、颁发机关、有效期或授权文书；[web/api/_privateDb.js](https://github.com/wpuu/MedicalChannelAI/blob/a85d6c9faa8dab1e6bd63dc7691facb13726f5b7/web/api/_privateDb.js#L81-L90)私有产品能力表只有关键词与能力类型。 | `DIRECT_AUTHORIZED`等是**客户所填能力类型**，并非独立证书/授权的有效性证明；不能自动转为`SATISFIED`。当前也**没有获授权的资料上传/持久化新流程**。 |
| **模型及人工边界** | [web/api/ai/_decisionContract.js](https://github.com/wpuu/MedicalChannelAI/blob/a85d6c9faa8dab1e6bd63dc7691facb13726f5b7/web/api/ai/_decisionContract.js#L114-L128)仅要求核实资格；[web/api/ai/_decisionContract.js](https://github.com/wpuu/MedicalChannelAI/blob/a85d6c9faa8dab1e6bd63dc7691facb13726f5b7/web/api/ai/_decisionContract.js#L173-L188)明确结构化快照未覆盖的条件不可补全；[web/api/ai/_decisionContract.js](https://github.com/wpuu/MedicalChannelAI/blob/a85d6c9faa8dab1e6bd63dc7691facb13726f5b7/web/api/ai/_decisionContract.js#L283-L312)禁止模型写事实理由、资格承诺。 | 现有AI只可支持“下一步核对哪些资料”，**不是具备法律/官方认定权的资格评估器**。不得用评分、关系、人脉或模型结论代替官方与私有证明。 |
| **历史规则样例** | [docs/strategy/ACTION_RADAR_GOLDSET_2026-10-07.md](https://github.com/wpuu/MedicalChannelAI/blob/a85d6c9faa8dab1e6bd63dc7691facb13726f5b7/docs/strategy/ACTION_RADAR_GOLDSET_2026-10-07.md#L1-L16)是`RULE_SMOKE_DRAFT / NOT_EXECUTABLE_BENCHMARK`；G01、G05的入围/经营/注册/厂家授权材料为历史示例（[docs/strategy/ACTION_RADAR_GOLDSET_2026-10-07.md](https://github.com/wpuu/MedicalChannelAI/blob/a85d6c9faa8dab1e6bd63dc7691facb13726f5b7/docs/strategy/ACTION_RADAR_GOLDSET_2026-10-07.md#L42-L50)，[docs/strategy/ACTION_RADAR_GOLDSET_2026-10-07.md](https://github.com/wpuu/MedicalChannelAI/blob/a85d6c9faa8dab1e6bd63dc7691facb13726f5b7/docs/strategy/ACTION_RADAR_GOLDSET_2026-10-07.md#L86-L96)）。 | 已有“未确认资格=UNKNOWN”的原则，可复用；但**这些不是本轮实地取得的血细胞分析仪官方完整资格条款，也不是运行成功证明**。不能生搬示例当每个项目统一要求。 |

**限定结论：** 本轮没访问或下载任何实时官方公告、招标文件/附件、客户证书/厂家授权，没有新的真实样本；只能提出**待实现的证据合同**，不得报告任何当前天津血球仪商机或客户资质“已满足”。

## 3. A03 标准：资格不是产品相关性，也不是截止时间

三个独立坐标，不能合并成一项状态：

1. **产品相关性**：沿用A01/A02`IN_SCOPE/OUT_OF_SCOPE/NEEDS_EVIDENCE`。明确整机仅是待核项目入口，不能自动变为投标资格合格。
2. **资格材料预核**：本文限定的`SATISFIED/NOT_SATISFIED/UNKNOWN`，是基于特定**项目、包件、公告版本、评估时点和明确证据**的资料匹配结论，**不是官方最终审核结论**。
3. **行为/时间窗口**：报名、获取文件、投标和采购意向阶段由已存在时间链单独判断；即使某项材料预核匹配，已错过窗口也不得显示“现在可正常报名”。反之，窗口开放也不证明资格满足。

### 3.1 必要输入与 provenance（仅设计；当前结构不存在）

每个**官方要求条目**拟需要：`project_id`、`package_id`（公告若有分包）、`notice_version/attachment_version`、官方HTTPS链接、原文短摘与页/条/表格定位`locator`、是“硬资格/技术参数/提交材料/其它”的类型、适用主体、是否硬性、是否可替代、公告/附件完整性及版本核对状态、核验时点。**禁止仅根据标题生成要求**。附件无法读取/有缺失/修订版本不确定时`requirements_complete=false`。

每条**客户私有材料**拟需要：**客户明确许可的**材料或确认来源、所属`organization_id/user_id`、材料主体（经销商/制造商/具体品牌型号）、证书/授权类别、编号或受控引用、签发/有效起止、适用范围和包件、客户最近确认时间、校验人/校验方式、原件真实性及可用性状态。**不在公共快照中放原件或号码**；本轮不设计新上传API、库表迁移或真实资料读取。用户口头自报或选了`DIRECT_AUTHORIZED`只作待核线索。

只有**官方招标原文确实要求**，才创建对应类别的条件；可能类别包括主体营业/经营资质、医疗器械相关产品注册/备案、厂家授权、明确的三/五分类整机技术参数、特定地区/平台入围及财税信用/案例等。它们是**条件分支示例，不是所有血球仪招标必备清单或本轮查到的真实条款**。

### 3.2 每条规则的三态

| 状态 | 前提（针对同一项目/包件/官方版本） | 前台允许显示 |
| --- | --- | --- |
| `SATISFIED` | 官方条款已明确、来源和最新适用版本可定位；客户授权的证明主体/品牌型号/范围与条款**逐项一致**；证据真实性核验有记录，评估时点仍有效；若有替代路径须按原文核实；不存在未解决的冲突。 | “本项资料预核匹配（非采购方资格确认）”，附**官方定位+私有证明引用+有效期/待人工确认**；不得写“可直接投标”。 |
| `NOT_SATISFIED` | 存在**明确、可核验且目前没有合规有效替代**的反证，例如客户确认不具备某项强制授权、材料明确不是要求的主体/产品、失效且无其他有效材料；反证与当前版本条款一致。 | “存在明确不符合条件”，指出哪项被什么依据否决，建议补正或人工复核；**不能仅因用户未提供资料就判不满足**。 |
| `UNKNOWN` | 官方详情/附件未封存或不完整；客户证明未给/仅自报/未取得保存许可；包件、品牌型号、主体或有效期不明；校验方法不明；证据互相矛盾、来源过期、官方更正未复核；任何一个必要事实未确认。 | “资格待核”，清楚列出“缺哪条官方要求/哪项客户证明/哪项有效期”，点击现有官方依据入口自行核实，不补造。 |

**聚合决策规则（设计，未实现）：**

- 如果官方版本或要求全集尚未证实完整，整体必须`UNKNOWN`，即使某个条目看上去匹配；可另外列“已知存在的风险”，但不宣布全包满足。
- 在完整、有效的官方适用版本下，如任何硬条款有已确认且无有效替代的反证，则整体`NOT_SATISFIED`；若冲突/替代可能性未排除则`UNKNOWN`。
- 只有**所有适用硬条款都逐项`SATISFIED`且官方要求全集完整**，才能给“资料预核匹配”`SATISFIED`；仅有部分证明时整体`UNKNOWN`。非硬性材料可单独提示，不暗中当硬资格。
- 公告更正、附件版本变化、客户证明到期、组织/品牌/包件变化时，原结论**失效并重新`UNKNOWN`**，不得继承旧“满足”。
- **负面例外**：对可能影响投标的资格反证，哪怕归类`UNKNOWN`，也必须作为“待核明确风险”展示；不得静默排序为可投。

### 3.3 信息保护与最小验收字段

前台每条显示：`资格项`、`资格预核状态`、`官方原文位置`、`客户证明类别（不公开号码/全文）`、`证据有效期或UNKNOWN`、`必须人工确认事项`。整体状态旁固定“**不代表采购单位最终资格审核**”。官方事实与客户私有资源独立，不允许匿名或跨账号看到证书、号码、医院关系；本轮**不实际创建或储存**这些数据。

## 4. A04 唯一最小开发授权卡（待用户另行批准）

**A04 名称：详情页“资格待核”只读门禁与确定性合成合同**。

**为什么先做它：** 目前真实公开快照没有结构化资格要求、私有Profile没有证照文件。直接做“自动资格通过”必然无事实基础。A04能先阻断“整机相关=可投”的误解，明确说明缺什么、让用户打开现有`EvidenceCard`核对官方。纯函数在离线合成完整证据对中可验证三态规则；**现阶段所有真实页面若没有新增获核验资格字段，只能显示`UNKNOWN`，绝不通过用户自述或高分推SATISFIED**。它不做资料上传或新数据库。

**拟精确触及四个应用文件（仅建议，不授权）：**

1. **新增** `web/src/utils/qualificationEvidenceGate.js`：无网络/无存储的纯函数，输入“完整性已核验证明的官方条款集合＋同一客户经许可的证据摘要＋评估时间”，输出逐项与整体三态及缺口。对当前卡片没有这些数据时必返`UNKNOWN`。完整性/更新/主体/包件/有效期/互斥证据采取严格保守规则；不会影响A01整机判别。
2. **新增** `web/src/utils/qualificationEvidenceGate.d.ts`：限制输入输出类型及状态、来源定位、证据有效期、受控显示字段；不得声明不存在的已发布API字段。
3. **仅局部修改** `web/src/pages/OpportunityDetailPage.tsx`：在已有官方依据/产品范围与私有资源旁展示一块**“投标资格待核”**说明、当期缺少官方资格条款与客户证明的具体核对步骤，以及现有官方来源入口。该页面**不允许上传、保存、外发、查询实时数据库或输入证书号**，不改AI、跟进、评分、Today和商机池行为；历史快照不得输出当前资格结论。
4. **新增** `web/scripts/check-qualification-evidence-gate.mjs`：纯本地Node断言；无新依赖、不调用项目模型、SDK、网络或数据库。测试模拟数据仅用于逻辑边界，不能冒充真实客户/官方结果。

**拟定向案例（本轮未执行）：**

| 编号 | 合成条件 | 应得状态 |
| --- | --- | --- |
| Q01 | 无官方资格字段/附件 | `UNKNOWN` |
| Q02 | 只有已核验整机标签/AI高分/`DIRECT_AUTHORIZED` | `UNKNOWN` |
| Q03 | 官方资格条款不完整，客户单项证照有效 | 整体`UNKNOWN` |
| Q04 | 官方版本和包件明确，单个硬资格所需证书未提供 | `UNKNOWN` |
| Q05 | 客户提供但证书颁发/主体/真实性尚未确认 | `UNKNOWN` |
| Q06 | 官方要求厂家授权，客户明确确认**没有且无合规替代** | `NOT_SATISFIED` |
| Q07 | 要求某包件证照，已证明是另一包件/另一组织且无有效替代 | `NOT_SATISFIED` |
| Q08 | 有效且匹配的一项条件，但其余资格未知 | 整体`UNKNOWN` |
| Q09 | 版本封存、全部硬条款齐、主体/品牌/型号、有效期与授权证据全匹配 | `SATISFIED`，标签仍非最终投标资格 |
| Q10 | 有新公告更正/客户证书失效 | 旧`SATISFIED`降为`UNKNOWN`直至重新核验 |
| Q11 | 正反证据冲突、证明存替代可能未查清 | `UNKNOWN` |
| Q12 | 资格资料匹配但报名期限已过 | 资格独立判断，不给“目前可报名” |
| Q13 | 跨组织/另一客户证书 | 不得复用，`UNKNOWN` |
| Q14 | 采购意向尚无正式资格附件 | `UNKNOWN`，不说已公开招标 |
| Q15 | 官方要求根本不包括“厂家授权” | 不凭常识追加该硬资格 |

**验收与退出条件（A04获新授权后）**：先确认GitHub最新HEAD、原工作树/在途改动，复用已有功能；只实施上列四文件；运行新增定向Node断言和在已有依赖可用时的`npm run typecheck`；无依赖不安装。若逻辑证明或界面需要修改后台、Profile、DB、配置、任何其它页面/组件，立即停止扩范围并提出新授权。提交代码结果仍**不是B3的真实业务PASS**。

**A04明确不在授权范围**：采集/解析资格附件、Profile证书记录/上传、持久化、实际双账号隔离验收、客户联系、在线Preview/Production、AI生成、资格法律保证、修改计划/DNS/环境、测试旧1213/10/3。上述都需新证据和单独授权；SDK和强保证分支继续CLOSED NO-GO。

## 5. 停止与交接

本轮仅可修改本报告与四份交接文档。A01/A02实际Node/TypeScript门禁仍未完成（不为补证新建环境），B1–B6均`NOT_VERIFIED`，真实d Preview`NO-GO_PAUSED`，SDK/强保证`CLOSED_NO_GO`，`production_ready=false`、`apply_allowed=false`、`migration_usable=false`。不触发采集/模型/云端测试，不下载真实公告附件，也没有3家真实试用客户。

**唯一下一任务：等待用户另行明确批准A04四文件离线切片；未经批准不改应用，也不反复生成相同A03审查。** 推荐GPT-6.1 Sol High；本轮实际模型和思考等级未核实。
