# MED-ACTION-20261030/C02｜采购包级官方事实修复与自动采集证据验收

任务状态：READY_FOR_ISOLATED_IMPLEMENTATION / NOT_AUTHORIZED_FOR_PRODUCTION
研究起点：docs/research/2026-10-30/C01_market_gap_audit.md
回归事实：docs/research/2026-10-30/C01_same_hospital_package_fixture.json
旧安全基线：PR #75、PR #78（尤其来源窗口、Queue 续批、fail-closed 和部分提交约束）
执行原则：只建隔离候选分支，先审查再施工，不合并 main、不部署 Production、不改 Cron/Secrets/付款和账户。

## 任务 A：定位并修复天津 CCGP 包级产品格式

目标是补官方主公告已经写明但系统目前没有抽取出的产品名。不要扩充全国 Collector。

已定位路径：web/pipeline/medical_channel_pipeline/ccgp_detail.py
- _extract_standard_product_table_items 目前要求 品目名称、采购标的、数量 等；
- _extract_bounded_procurement_demand_items 只接受明确产品和数量；
- _extract_package_products 不支持“第1包 是 248 227 临床检验设备 采购血气分析仪等”的表格行。

请先基于真实官方页面，复现解析结果 product_items=[]，并记录真实 HTML hash、源网址和受支持的表头/行结构；若无法合法读取官方 HTML，停止真实数据宣称，只能使用标记为 OFFLINE_SYNTHETIC 的最小 fixture。

新增有明确 boundary 的 package-table adapter，必须保持：
- 官方域名与原文来源校验；
- 固定表头：包号、是否设置最高限价、预算（万元）、最高限价（万元）、采购目录、采购需求；
- 行对应 package_id；
- 预算、限价按单位换算并校验；不要把包预算当某产品预算；
- 从采购需求里明确的产品短语抽取名字，无数量时 quantity=null；
- 有“等”/附件时 coverage_status 保持 PARTIAL，不假定八个产品就是全部清单；
- 不能把项目名/医院名/附件说明冒充设备名称；
- 与旧解析器结果必须按证据融合，不允许新弱抽取覆盖旧强事实；
- 保持 source evidence span；任一模糊项降级人工复核。

优先验证：XCSD-2026-A-939 第五批的四个包、八个主公告明示名称和预算/限价。
随后验证：
- 第一批 A-942：全自动生化免疫流水线；
- 第二批 A-943：免疫流水线、全自动酶免仪；
- 第四批 A-944：生物显微镜/医学显微镜/生物安全柜、冷藏加冷冻医用冰箱/负80度冰箱。
三批目前只有二级转引，必须重新核实官方原文后才能宣称 VERIFIED。

## 任务 B：硬负例和包级回归

新增测试至少覆盖：
1. 第五批四包完全不混包，四个包不同预算/最高限价正确；
2. 缺数量时 quantity=null，不凭常识补“1台”；
3. 包含“等”的项目标记清单非穷尽；
4. 只读附件名称不能自动创造设备清单；
5. 非医疗采购安防/教学模型不能错误匹配医疗产品；
6. 非官方页面与表头不匹配的“伪采购表”不纳入 verified facts；
7. 第三方聚合提供与官方冲突的截止日期时要标 source_conflict，保持官方期限；
8. 完整历史 parser 回归无新增失败；
9. main 基线失败和新增失败分开统计。

## 任务 C：生产自动采集门禁（只读诊断）

10/30生产事实：snapshot 10/28 08:27 STALE；pipeline-health 503；collector-status v2 0/22、chain=null、各源 scan=null。

不要直接清缓存、重置 Queue、重启 Cron 或用人工发布掩盖状态。

核验链：
Cron触发 → Queue accepted → source start → official discovery/detail → canonical persisted → durable snapshot readback → source freshness status。

阅读 PR78（Draft、不活跃），特别要避免将旧 P0 的新增源 patch 粗暴合并，导致已设计的完整窗口/分页校验、<=3 详情每批和整源 fail-closed 不可用。

要求用新独立证据判断具体阻塞位置；尚无法确认 Cron 根因时如实报告 UNKNOWN。

## 放行条件

- 可重演第五批四包全部明示产品，预算/最高限价与主公告逐包一致；
- 关键事实无编造，原文不可读时不升级 VERIFIED；
- 失败时保留旧完整 canonical/snapshot；
- 最低一轮完整单测和 Preview smoke 通过，但 Preview READY != 生产通过；
- 生产运行必须另有授权并连续7天源级证据；
- 缺任一关键证据则结果是 HOLD，不要宣称商业可售。

完成回报：分支、起始SHA、最终SHA、修改范围、实测日志摘要、对照 JSON 差异、已确认/未确认原文、失败点、是否触碰 Production（必须 NO）、下一步商用门槛。

推荐模型：GPT-6.1 Sol High；涉及跨 PR75/PR78 的 Queue/源时间窗/状态机冲突，切换 Extra High。
