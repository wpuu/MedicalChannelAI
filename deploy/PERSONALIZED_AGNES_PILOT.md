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

后续每天复用同一客户画像，不要求重复填写；客户修改画像后立即重新匹配。

## 真实 Pilot 首次启动顺序

真实 Pilot 不把 Vercel verified Demo 里的演示客户关系或预写 AI 结论复制到数据库。

顺序固定为：

```text
部署代码与 H5
  ↓
配置 canonical origin + Agnes server-only key
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

登录成功默认进入 `/profile`，不是 `/today`。账号首次兑换后从 `INVITED` 变成 `ACTIVE`；Session 默认最长 30 天。

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

当前受控 taxonomy 已包含：

```text
PHLEBOTOMY_COLLECTION_TABLE = 采血台 / 智能采血工作台
```

这用于亚虎/采血业务相关商机的确定性匹配，不由 Agnes 自由猜分类。

## Agnes 调用边界

1. 先做确定性事实校验、画像匹配和经营优先级；
2. 最终最多 5 个需要解释的候选才进入 Agnes；
3. 浏览器 GET 刷新使用稳定 task identity，不重复创建同一模型任务；
4. Worker 受 global lease、start spacing、in-flight 约束；
5. Agnes 只能基于锁定的官方事实 + 客户确认资源输出；
6. 输出必须通过 action allowlist、supporting facts/profile paths 和 grounding 校验；
7. 校验失败显示 `MODEL_OUTPUT_REJECTED`，不能伪造 READY；
8. 页面只收到 public view，不收到 model_input、provider、key、task_id 等内部字段。

## 前端行为

真实 API Service 对 `AWAITING_MODEL` 做短轮询；用户打开 `/today` 后，若 Agnes 很快完成，会自动拿到 READY 结果。

如果短轮询结束仍未完成，页面保留真实状态，不编造建议。后续刷新仍复用同一任务，不重复启动 Agnes。

## 当前不能宣称的内容

在完成真实服务器联调之前，不得宣称：

- 已经线上调用 Agnes 成功；
- Python deterministic tests 已 PASS；
- 老杨账号已经可用；
- 天津公开采购已全量实时覆盖；
- `production_ready=true`。

Vercel Preview / `medicalchannelai.vercel.app` 只承担当前 H5/verified Demo，不运行 Python API / systemd Agnes Worker。
