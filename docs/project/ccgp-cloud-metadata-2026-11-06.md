# d关联Preview非敏感云端元数据核实

2026-11-06，北京时间22:05:50开始，前台截止22:25:50。起点1238596a93d5ff2ec56ac61ecba219ba8cce8b87，工作树干净，仅根代理运行，无附着终端任务。已读取用户新增授权及工作约定、current-state/checkpoint、next-task、守卫和接入审查报告。本轮只获准查询指定项目/d关联既有Preview的非敏感元数据，没有获准真实缓存、数据库或业务接口访问。

## 实际云端观察

使用现有Vercel认证连接的`vercel_list_deployments`，过滤固定为：项目prj_7fk44eKUhdbfTUaXxEBMgIzZiqUM、team_jEy8Ex9vRDBdXj1cQPKF8sRd、分支codex/p0-reliability-contracts、来源82cc43f06c774969eab0fe44f0afc012f37cadac、target=preview、limit=1，以及历史部署创建时刻前后各1毫秒的窗口。没有列举其他项目、旧c或Production记录。

北京时间**22:09:25–22:09:26**提取到一条指定记录：

| 字段 | 提供商返回值 |
|---|---|
| deployment ID | dpl_8Jhc4imHEd6ndBUoth5xBVTrAyL1 |
| name / state | medicalchannelai / READY |
| URL | medicalchannelai-b5vc26me3-rerisse7-1717s-projects.vercel.app |
| target原值 | null，保留原值，不改写为preview |
| 创建时间 | 2026-11-06 19:25:23.837（北京时间） |
| meta.githubCommitSha | 82cc43f06c774969eab0fe44f0afc012f37cadac |
| meta.githubCommitRef | codex/p0-reliability-contracts |
| meta.githubOrg / githubRepo | wpuu / MedicalChannelAI |

这是**指定既有部署在本次查询时的元数据**，不是对项目所有部署的盘点，不证明它是整个项目或所有d关联部署中的最新版本。READY不表示本轮浏览器/函数/数据面健康验收通过。记录未独立返回projectId/teamId/ownerId；只证明指定team/project过滤上下文查询命中，不能据此替代项目所有权或Runtime Cache后端身份认证。Preview是请求筛选条件，provider target=null也不是d epoch或数据库实际注入值的证明。

## 工具返回范围与实际调用

遵循[Vercel部署检查技能](skill://plugin_connector_690a90ec05c881918afb6a55dc9bbaa1/deployments-cicd/SKILL.md)中检查不授权发布的边界。先查看工具契约，选择部署列表摘要，未调用没有安全字段投影约束的get_project/get_deployment，未调用env、日志、文件内容、分享/绕过或web_fetch接口。

本次受控批次共**4次只读云端调用**：

1. 22:07:47–22:07:48，限定部署摘要查询。工具响应为多层包装，首次本地解析未解包，未据此判断为空。
2. 22:08:38–22:08:39，相同筛选复核，仍未提取到嵌套列表。保存为解析未完成，不当作无部署。
3. 22:09:25–22:09:26，相同筛选，按`result.deployments.deployments`提取上表记录；只保留白名单字段。
4. 22:10:44–22:10:45，对该已命中部署调用list_deployment_files，仅请求源文件目录元数据。接口返回`not_found`，无文件目录证据；未重试、未执行返回的CLI fallback、未读取文件内容或构建日志。

前两次是本地响应提取失败，不是部署为空、云端业务故障或验收通过；相关尝试明确保留。目录失败也**不证明部署不存在、源码为空或SDK未安装**。云端读取到此停止。见[请求及提取记录](validation/ccgp-cloud-metadata-2026-11-06/query-attempts.json)、[部署白名单摘要](validation/ccgp-cloud-metadata-2026-11-06/deployment-summary.json)、[目录结果](validation/ccgp-cloud-metadata-2026-11-06/deployment-source-tree.json)。

## 本地源码交叉核对与go/no-go

以云端记录声明的82cc43f SHA查询已有本地Git对象，不访问Git远端：该提交没有web/collector_readonly_export.py或web/collector_readonly_guard.py；pyproject.toml仅声明`vercel`，没有准确版本，也没有查询到指定Python锁文件。只读业务入口源码为既有collector-run/queue/status/pipeline-health，不能当任意get-only执行通道。没有读取部署bundle或执行代码，因此只得出**声明源码不含内核/守卫**，不把本地树当已验证部署bundle字节。

| 条件 | 本轮结论 | 对真实接入的影响 |
|---|---|---|
| 指定部署记录/状态/声明来源 | 已核实上述摘要 | 允许引用这一个记录，不能声称项目最新部署已核实 |
| 项目/团队归属 | 指定过滤上下文命中，独立所有权字段未返回 | 不充当运行缓存身份认证 |
| Preview/d实际运行标识及数据库绑定 | provider target=null；实际epoch/数据库值未读取，未核实 | NO-GO，不假定d身份成立 |
| 部署是否含605ebad守卫/9781921内核 | 声明来源82cc43f的本地Git树不含二者；bundle未验 | 不能将本地1031通过当作已部署能力 |
| 实际已安装SDK版本 | 未核实，源码依赖未锁，云端目录不可得 | NO-GO，不用本地包版本或公开最新版替代 |
| Runtime Cache后端/租户/区域/签名身份 | 未核实，未请求任何凭据/claims/cache | NO-GO，元数据连接的权限不是Runtime Cache权限 |
| 既有安全执行通道与强制超时/响应大小能力 | 未核实；没有执行函数、创建入口或环境 | NO-GO，不把应用status或Queue当维护执行通道 |
| 58键/116次真实观察 | 未执行且本轮未授权 | NO-GO，不能扩大本次元数据授权 |
| 迁移/CAS/真实回滚 | 未实现/未执行，原子revision与语义覆盖仍缺 | 独立NO-GO，apply_allowed/migration_usable=false |

## 验证与权限结果

本轮只修改文档和本地验收artifact，没有修改应用、内核、守卫或测试，没有重跑代码未变的1031/10/3；这些仍是605ebad绑定的历史门禁。**314份**起点原始data、fixtures与旧validation文件字节不变，源码和测试也不变。新证据保存非敏感筛选参数、白名单响应、目录错误、源码交叉核对、完整性hash和时间，没有凭据、环境变量值或原始构建日志。

Runtime Cache/数据库读写0、项目业务HTTP调用0、函数/Queue/模型调用0；没有新建环境、部署、推送、改计划/变量/凭据/权限/保护或新增路由。没有访问旧c/Production或扩大项目。云端scope仅此一次元数据核实；scope_provenance_verified、apply_allowed、migration_usable均false。[证据清单](validation/ccgp-cloud-metadata-2026-11-06/manifest.json)。

下一步见[next-task.md](next-task.md)：只读审计**官方公开Python SDK的文档/包源码**，确认归属后锁定一个待审候选版本/哈希，核查get、物理键、身份来源、timeout/重试/取消和大小上限；不安装、不导入运行SDK、不接触项目凭据或数据、不部署。它将补齐第三方SDK能力证据，不是继续增加模拟层，也不能冒称核实了该部署实际SDK版本。公开来源访问不在本轮项目元数据授权中，须取得下一轮明确授权后再做；本轮未执行。当前界面无法生成该按钮；提供完整可复制提示词，推荐GPT-6.1 Sol高（high），实际设置未核实。
