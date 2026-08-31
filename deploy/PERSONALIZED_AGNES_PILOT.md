# Personalized Agnes Pilot

Status: `FROZEN_FOR_TIANJIN_PILOT_2026-08-31`

本文件覆盖旧的“老杨先看无登录静态 Demo / zero-config 后再录资料”产品路线。

## 老杨实际使用路径

```text
管理员创建试用客户
  ↓
一次性邀请注册链接
  ↓
首次注册 / 激活
  ↓
/profile 填医院关系、产品能力、品牌/厂家资源、渠道/租赁能力、项目偏好
  ↓
PUT /api/profile
  ↓
服务器重算 profile readiness
  ↓
立即重算 Today Actions + 幂等写入 Agnes queue
  ↓
常驻 Agnes worker 消费最多 Top5 的 grounded 任务
  ↓
READY / BLOCKED / REJECTED
  ↓
H5 /today 显示个性化行动、理由、风险和官方依据
```

画像达到候选条件后，H5 保存成功直接进入 `/today`。后续每天复用同一客户画像，不要求重复填写；客户修改画像后立即重新匹配。

## 真实 Pilot 首次启动顺序

真实 Pilot 不把 Vercel verified Demo 里的演示客户关系或预写 AI 结论复制到数据库。

顺序固定为：

```text
部署代码与 H5
  ↓
配置 canonical origin + Agnes server-only key
  ↓
先跑隔离 Agnes provider smoke
  ↓
启动 API + Agnes Worker
  ↓
用官方详情 URL manifest 走正式 Collector 导入首批真实公开项目
  ↓
创建 INVITED 客户账号
  ↓
发送一次性注册链接
  ↓
客户填写真实画像
  ↓
真实 Agnes 产生个性化 Today Top5
```

## 服务端环境

`/etc/medicalchannelai/pilot.env`：

```text
MCAI_CANONICAL_ORIGIN=https://<pilot-domain>
MCAI_AGNES_API_KEY=<server-only-key>
# 通常留空，使用客户端默认 allowlisted 官方端点。
# 如确有需要，只能使用代码 allowlist 中的官方地址，例如：
# MCAI_AGNES_BASE_URL=https://apihub.agnes-ai.com/v1
```

`MCAI_AGNES_API_KEY` 只能存在服务端环境。禁止进入 H5、SQLite 客户画像、GitHub、日志、URL 或浏览器 LocalStorage。

## 先跑隔离真实 Agnes provider smoke

在启动老杨真实账号之前，先验证服务器网络、Key、官方 Agnes endpoint、exact JSON 输出和正式 grounding validator。

新增命令：

```bash
cd /srv/medical/app
set -a
source /etc/medicalchannelai/pilot.env
set +a
sudo -E -u medicalai python3 -m tools.medical_pilot.agnes_provider_smoke
```

该 smoke：

- 使用固定**合成** grounded input，不读取老杨或任何真实客户资料；
- 默认使用临时 SQLite，仅保存该次 smoke 的 global lease state；
- provider start 仍必须先取得正式 global lease，不绕过 12/min、start spacing、in-flight 规则；
- 调用正式 `AgnesChatClient`；
- 输出必须通过 `validate_model_decision`；
- 无论模型成功还是失败都会释放 lease；
- 不输出 API Key、provider response body、model input 全文或客户资料。

成功输出只包含类似：

```json
{"status":"PASS","provider_call_executed":true,"contract_validation_passed":true,"action_type":"..."}
```

只有看到 `status=PASS` 才可以把“真实 Agnes provider smoke”记为通过。没有 `MCAI_AGNES_API_KEY`、401/429/5xx、网络错误、非 exact JSON、越界 action/reason/fact 引用都不能记 PASS。

## 必须真实运行的进程

真实 Pilot 至少需要同时运行：

```text
medical-pilot.service          # /api 后端、Session、profile、Today Actions
medical-agnes-worker.service   # Agnes Today Actions queue worker
```

只启动 `medical-pilot.service` 不算 Agnes 闭环完成：API 会排队，但没有 Worker 消费。

```bash
sudo cp deploy/medical-pilot.service /etc/systemd/system/
sudo cp deploy/medical-agnes-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now medical-pilot.service
sudo systemctl enable --now medical-agnes-worker.service
sudo systemctl status medical-pilot.service --no-pager
sudo systemctl status medical-agnes-worker.service --no-pager
```

两个进程必须指向同一个持久 SQLite：

```text
/srv/medical/data/pilot.sqlite
```

当前 SQLite queue/lease/result store 只作为单机/同主机多进程 Pilot 方案。跨机器横向扩容前必须换共享原子存储。

## 首批真实公开项目：必须走正式 Collector

初始化 manifest：

```text
deploy/tianjin-pilot-bootstrap-urls-2026-08-30.json
```

它只保存已经核实的官方采购详情 URL + expected project code，不保存：

- 客户医院关系；
- 产品/厂家资源；
- 演示优先级；
- 预写 Agnes 结论；
- API Key 或任何内部凭据。

首次导入：

```bash
cd /srv/medical/app
sudo -u medicalai python3 -m tools.medical_pilot.pilot_live_seed \
  --db /srv/medical/data/pilot.sqlite \
  --manifest deploy/tianjin-pilot-bootstrap-urls-2026-08-30.json
```

每条数据执行：

```text
registered official URL
→ HostBoundFetcher
→ parser
→ VERIFIED event/facts
→ expected project code check
→ event ledger
→ current lifecycle projection
→ controlled product classification
→ institution enrichment
→ Today repository
```

项目编号不匹配时，必须在持久化**之前**失败。

无法从官方事实确定产品细类、机构类型或其他关键字段时保持 `UNKNOWN / NEEDS_MORE_FACTS`，不能为了让 Agnes 有结果而人工猜分类。

退出码：

- `0`：manifest 全部导入成功；
- `1`：部分成功；
- `2`：全部失败。

输出只包含公开、安全摘要和异常类型，不输出网页正文、客户资料或模型输入。

当前已在隔离 Vercel live 环境真实执行5条官方 URL：`5/5` 成功。真实 Pilot 主机仍需再执行一次，以验证目标主机自己的网络和持久 SQLite。

## CCGP 采购需求 grounding

中国政府采购网公告的产品分类不能只靠标题，也不能把整页 HTML 喂给分类器。

当前链路新增：

```text
tools/medical_pilot/ccgp_procurement_demand.py
```

只从明确 `包号 + 采购需求` 表格的合法包号行生成 VERIFIED `product_item` facts。资格条件、政策说明、联系人等页面文字不会被提升为产品事实。

`XCSD-2026-C-181 / 病原微生物能力提升相关设备购置` 已在真实 live bootstrap 中得到以下受控分类：

```text
LAB_NGS_SEQUENCER
LAB_AUTOMATED_LIBRARY_PREP
LAB_METAGENOMICS_ANALYSIS
LAB_MICROBIAL_MASS_SPECTROMETRY
LAB_BIOINFORMATICS_COMPUTE_APPLIANCE
```

## 创建一个可直接填写资料的客户

不再手写完整 profile JSON。管理员执行：

```bash
cd /srv/medical/app
sudo -u medicalai python3 -m tools.medical_pilot.pilot_admin \
  --db /srv/medical/data/pilot.sqlite \
  bootstrap-invite \
  --company '天津试用客户' \
  --ttl 1800 \
  --login-url 'https://<pilot-domain>'
```

`--tenant` 可省略，由服务器自动生成。

输出中的 `login_url` 只发给目标客户，不贴 GitHub / Issue / 日志。一次性邀请码用后失效。

登录成功默认进入 `/profile`，不是 `/today`。账号首次兑换后从 `INVITED` 变成 `ACTIVE`；Session 默认最长30天。

## 首次画像只录真正影响判断的信息

- 天津经营范围；
- 主要客户类型；
- 产品/品类能力；
- 品牌、厂家或临时找厂家能力；
- 渠道合作能力；
- 租赁能力；
- 最低值得跟进项目金额；
- 希望优先看的采购阶段；
- 已确认的医院/科室关系及关系强度。

当前 H5 已暴露包括以下 controlled taxonomy：

```text
PHLEBOTOMY_COLLECTION_TABLE = 采血台 / 智能采血工作台
LAB_NGS_SEQUENCER = 基因 / 高通量测序设备
LAB_AUTOMATED_LIBRARY_PREP = 自动化建库设备
LAB_METAGENOMICS_ANALYSIS = 宏基因组分析系统
LAB_MICROBIAL_MASS_SPECTROMETRY = 微生物飞行时间质谱
LAB_BIOINFORMATICS_COMPUTE_APPLIANCE = 生物信息 / 生物计算一体机
```

这些稳定 ID 用于确定性产品能力匹配，不由 Agnes 自由创造分类。

## 真实附件 probe

官方天津财政附件 URL 已确认，但 Vercel US 两次读取分别在约20秒、60秒超时，尚未拿到真实 bytes。因此当前附件 binary capture 仍为0。

真实 Pilot 主机可执行：

```bash
python3 -m tools.medical_pilot.attachment_live_probe \
  --url 'https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=1OQ5vSM9GqM%2A&method=downEnId' \
  --filename 'XCSD-2026-C-181项目需求书.docx'
```

只有输出真实 `status_code/content_type/size_bytes/sha256/parser_version` 后，才可以把该附件记为 binary/parser 已验证。

## Agnes 调用边界

1. 先做确定性事实校验、画像匹配和经营优先级；
2. 最终最多5个需要解释的候选才进入 Agnes；
3. 浏览器 GET 刷新使用稳定 task identity，不重复创建同一模型任务；
4. Worker 受 global lease、start spacing、in-flight 约束；
5. Agnes 只能基于锁定的官方事实 + 客户确认资源输出；
6. 输出必须通过 action allowlist、supporting facts/profile paths 和 grounding 校验；
7. 校验失败显示 `MODEL_OUTPUT_REJECTED`，不能伪造 READY；
8. 页面只收到 public view，不收到 model_input、provider、key、task_id 等内部字段。

## 前端行为

真实 API Service 对 `AWAITING_MODEL` 做短轮询；用户打开 `/today` 后，若 Agnes 很快完成，会自动拿到 READY 结果。

如果短轮询结束仍未完成，页面保留真实状态，不编造建议。后续刷新仍复用同一任务，不重复启动 Agnes。

## 当前可信验证

最新完整发现集已实际执行：

```text
478 Python unittest cases = OK
TypeScript tsc --noEmit = PASS
Vite production build = PASS
```

最新验证 deployment：`dpl_DK3P2jgaLHqfkGAFV6verUpHj9ZG` → `READY`。

这只证明 deterministic backend/H5/smoke harness 的代码门禁已通过，不等于真实 Agnes provider 已经调用成功。

## 当前不能宣称的内容

在完成真实服务器联调之前，不得宣称：

- 已经线上调用 Agnes 成功；
- 老杨账号已经可用；
- 真实附件 bytes/MIME/SHA/parser 已验证；
- 天津公开采购已全量实时覆盖；
- `production_ready=true`。

可以明确宣称：当前478个 deterministic unittest 已真实 PASS，5条官方 URL 的隔离 live bootstrap 已5/5 PASS。

Vercel Preview / `medicalchannelai.vercel.app` 继续承担当前 H5/verified Demo，不替代真实 Python API / systemd Agnes Worker。
