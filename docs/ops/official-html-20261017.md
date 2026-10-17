# 四页官方HTML受限取证与离线发现

状态：**FOUR_CAPTURES_SAVED_LOCALLY / IMPLEMENTATION_GAPS_CONFIRMED / RELEASE_BLOCKED**。

起点：PR78 `74f07dd6813db3c47bed42070aa24f8adc901794`；产品代码仍为`c0d0215d99a8f109cfe62a313f0bf6daf9d8a771`，PR75保持a2131e4。本轮仅取证、离线核对及保存元数据/文档，不改产品代码、parser或配置，不把历史164/879项检查当新HEAD CI。

## 授权、实际请求与本地原文

用户在“是否批准这一次4页只读取证”的明确范围后回复“继续”。仅执行以下4个已核对URL，各一次GET、20秒/1MiB、请求间隔至少3秒，不重试、不跟随重定向或分页，不运行页面JS。没有运行产品采集入口、模型、Queue或发布，没有线上数据写入。

| URL | HTTP | 原始字节 | 完成时间UTC |
| --- | --- | --- | --- |
| `https://www.tjzyefy.com/xwgg/ggtz/` | 200 | 105532 | 15:54:53.991499 |
| `https://www.tjzxfc.cn/ywgk/zbgg/index.shtml` | 200 | 12605 | 15:55:00.360361 |
| `https://www.tjzyefy.com/system/2026/09/28/030199113.shtml` | 200 | 98792 | 15:55:05.359647 |
| `https://www.tjzyefy.com/system/2026/09/30/030199248.shtml` | 200 | 94735 | 15:55:09.670000 |

日期均为2026-10-17，共311664字节。原始响应字节、头字段、每页URL/时间/hash、批准范围和一次性capture脚本保存在本地：

`/workspace/.medicalchannelai-onboarding/MedicalChannelAI/official-html-20261017/`

`.body`是未转码原文，`.decoded.html`是明确编码下严格解码后的UTF-8诊断副本；不得把二者hash混用。Git只保存[capture-summary.json](evidence/official-html-20261017/capture-summary.json)、[audit-result.json](evidence/official-html-20261017/audit-result.json)及离线审计脚本，**不上传四份原始HTML**，符合本次仅本地保存范围。取得原文不等于官方列表结构已审查注册，也不证明完整覆盖或上线成功。

## 具体发现与最小修复范围

1. **真实GB2312页面被当前transport拒绝。** 中心妇产响应头为`Content-Type: text/html`，没有charset；HTML meta声明gb2312，原始字节严格按gb2312可解码。把这些原始字节和实际响应头离线喂给当前`_worker_fetch`，稳定得到`OFFICIAL_PAGE_DECODE_FAILED`：当前代码在HTTP头缺charset时直接选择UTF-8。最小修复是受限、可追溯的header/meta编码选择及严格解码，保持字节/时间/类型限制，拒绝冲突或不支持编码，不使用`errors=replace`伪造成功。此次没有修改transport。
2. **当前列表shape不足以表示真实HTML。** 中医二附院公告在`td.hanggao26.zi14`内部的table行中，没有当前要求的ul/ol唯一id；中心妇产有`ul#xwzx-list`，但直接子元素是table，li内部还有table。两院每条记录均出现同URL嵌套`<a><a>…</a></a>`。当前中心妇产shape离线返回`OFFICIAL_INDEX_STRUCTURE_UNKNOWN`，属于正确阻断，不能据200放宽。最小范围是分别按已捕获真实行结构解析，只允许同一逻辑行内已确认的相同嵌套链接；跨行重复identity、侧栏和未知结构仍拒绝，不能全页去重后声称列表完整。
3. **第一页不足30日，真实分页尚未取证。** 对保存页做非生产、未scoped的诊断：二附院20个唯一公告URL，日期10月14日至10月9日；中心妇产10个，10月16日至10月12日。捕获时北京时间为10月17日，30日窗口为9月18日至10月17日，两页均未到起点。分页只有`div#pagetemple`和外部`count_page_list_…js`引用；本次不读取JS、不猜`index_N`、不跟页。没有实际分页范围及终点证据之前，覆盖门禁仍阻断。
4. **采购意向候选已超过现有整源上限。** 既有discovery在二附院第一页得到research 2条、intent 14条；中心妇产early-signal 1条。intent broad discovery有意先保留候选，详情再判断医疗范围，不能仅按标题扔掉14条中的未取证记录。仅第一页14条已经超过每源3详情上限；当前上限阻断保留，未伪造完整window调用stage，也未请求这14篇正文。后续需要在既有Queue/周期/canonical边界内设计可核对的续批完成门禁，保留每批预算与失败旧数据；不能简单截前三、提升为一次14请求或标成功。续批协议目前未实现，不引入新服务、来源、地区或架构。

## 两篇正文的离线核对

- 9月28日正文由既有research parser解析出stable ID `tjzyefy_20260928_030199113`、17项产品，截止`2026-10-09T16:00:00+08:00`。当前真实捕获时点的确定性actionability为`ARCHIVE / NOT_ELIGIBLE`；9月29日历史时间仅作离线对照为`PUBLIC_OPPORTUNITY`，不能把该时间当今日采集时钟或宣称当前ACTION_NOW。
- 9月30日数据安全正文未生成医疗记录：detail parser以`TJZYEFY_NOT_MARKET_RESEARCH`拒绝；用实际保存的标题/URL构造一个本地锚点，research discovery返回0。这个锚点明确是诊断构造，不是捕获的历史索引。没有吞掉未知解析错误、生成非事实成功stage或请求模型。
- 当前第一页不含这两篇旧公告；detail诊断中的expected_title取自真实正文title，published date取自URL。**历史index/detail配对未核实**，不能把成功解析的对象写为canonical、将其当完整核验记录，或以此推进source观察/覆盖时钟。

## 离线证据与未改变的门禁

可复核命令：

```bash
python docs/ops/evidence/official-html-20261017/audit_offline.py \
  --captures /workspace/.medicalchannelai-onboarding/MedicalChannelAI/official-html-20261017
```

脚本必须读已有四页及原始hash，禁止socket外连，没有抓取fallback。它核对四页边界、字符集失败、真实shape失败、第一页范围/候选数、正例deadline/当前归档和负例拒绝。保存结果是**新原文的离线诊断，不是新产品CI或完整测试套件**；没有重复164/879项、没有声称独立审查完成。原始HTML未入Git，缺本地资产时脚本会失败，不能伪称可从仓库独立复现。

三源仍未接入driver，22stage、history-only/partial及AI限制不变，官方contract注册表仍为空。当前产品问题是已确认的未激活候选缺口，**本次先报告证据和最小范围**。没有通过新注册表、复用旧种子、旧数据回填或伪造日期绕过保护。

[生产只读门禁](release-readback-20261017.md)仍有效：GitHub两条fallback在06:37Z为disabled_manually；Vercel实际Cron、唯一串行consumer/旧分区ready/in-flight/delayed/expiry、完整canonical/baseline库存及有效停止/回退仍缺。此轮没有重查生产，5:28/5:29Z的3216fd9与437条记录保留原时间。alias回退不停止Queue，旧生产回退目标不得删除；每天两次搜索仍未恢复。

**下一步**：在保持不联网、不激活的草稿中先修复受限编码选择和两院真实列表解析，继续明确30日覆盖不足；然后审阅既有Queue内的分批完成协议。分页JS/后续页不在本次4请求授权内，不能自动追加。原文继续仅本地保存，不自行将其发布到GitHub。建议 **GPT-6.1-sol · xhigh**；修复完成后再做必要边界检查及独立审查，不重复历史矩阵。
