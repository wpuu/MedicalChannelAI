# MED-ACTION-20261031/C04｜更正公告版本核验 + 自动采集可审计证据

接续：docs/research/2026-10-31/C03_implementation_and_provenance_audit.md
机器结果：docs/research/2026-10-31/C03_validation_evidence.json
工作分支：fix/c03-ai-clock-official-provenance-20261031
C03 已解决旧AI测试时间基准，Full CI 966 Python + prebuild/TS/Vite全部成功。
当前仍是 RELEASE_HOLD；不要把构建PASS当Production Ready。

## A. 官方更正与原件证据优先

目标项目 XCSD-2026-A-939（第五批）和同院 A-944（第四批）。
1. 只读查官方天津市政府采购中心/中国政府采购网，定位2026-10-30更正公告原文。
2. 明确把第三方索引“有更正公告”与官方更正正文拆开，不得从第四批更正内容推断第五批。
3. 在合法/可访问时获取官方10月27日HTML及原需求书DOCX、10月30日更正DOCX；保留SHA256、发布日期、公告版本关系、来源URL；不得绕403、验证码或付费权限。
4. 若官方附件需要用户在浏览器内手工下载，报告准确官方入口并把完整文件作为用户授权输入要求；未获取就维持UNKNOWN。
5. 先解析附件颜色标注所代表的具体更正，再决定产品/参数/报名/投标期限是否变动。
6. 做版本化回归：旧公告基础事实、官方更正覆盖字段、争议字段、未知字段；不能把旧版项目需求继续显示为最新可投。

## B. 包级产品解析真实来源验收

以官方真实HTML或官方DOCX（不是合成HTML）回放：
- 四包每包名称/预算/最高限价、主公告八个明示产品；
- 不得把包限价当设备单项价；
- 未公开的数量和型号标记UNKNOWN；
- 中文混合表、嵌套表、DOCX表格/颜色高亮更正；
- 保留链接回源和完整/部分覆盖标记；
- 部分失败时 fail closed，不能把未核验转引升级Verified。
如原件仍不可访问，则只能保持OFFLINE_SYNTHETIC_PASS，不许宣称真实解析完成。

## C. 采集器证据闭环（隔离开发、只读生产）

当前main只部署每天UTC00:20/北京时间08:20的一条Cron。
PR75/78双时段和25stage不是现有生产能力。

在代码/隔离测试范围：
1. 按Cron→Queue send→consumer delivery→source discovery/detail→canonical state→durable snapshot/readback逐点设计证据；
2. 使用最小无敏感字段、每周期唯一ID、源级状态/事件、SHA/timestamp与错误码；
3. 检查Queue至少一次投递/幂等、旧部署在途消息、stale lease、失败保留历史、来源完整时间窗；
4. 旧deep stage和PR78限<=3详情每批/整源完成前不发布的规则不能被削弱；
5. 设计7天无人干预真实执行验收，明确每天实际应该出现的检查点及失败报警，但本轮不得提交生产Cron/Queue变更。
6. Vercel Hobby日志保留不足以事后证明几天前自然运行，需耐久摘要落地到受控数据库/缓存，但要审计写入条件与版本并避免泄密。

## D. 验收与交付

- 先核GitHub最新 main/PR75/PR78，新的隔离实现必须关闭Vercel Preview自动触发；
- 运行聚焦+完整Python+TS+Vite+项目npm run build；无新增基线失败；
- 报告所有真实授权网页/附件原文是否取得，以及C04产出的官方更正对比表；
- 更新GitHub中文报告、源版本机器JSON、测试日志、下一门槛；
- 不合并main、不对Production部署或触发Cron、不发送消息/买标书/改密钥；
- 未满足源和自然Cron运行两个硬门槛之前，发布与收费Pilot仍HOLD。

执行结束给出下一步按钮，无需推荐模型和思考等级。
