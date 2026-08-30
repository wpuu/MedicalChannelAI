# Personalized Agnes Pilot

Status: `FROZEN_FOR_TIANJIN_PILOT_2026-08-30`

本文件覆盖旧的“老杨先看无登录静态 Demo / zero-config 后再录资料”产品路线。

## 老杨实际使用路径

```text
管理员创建试用客户
  ↓
一次性邀请链接
  ↓
首次登录
  ↓
/my profile: 填医院关系、产品能力、品牌/厂家资源、渠道/租赁能力、项目偏好
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

## 必须真实运行的进程

真实 Pilot 至少需要同时运行：

```text
medical-pilot.service          # H5 /api 后端、Session、profile、Today Actions
medical-agnes-worker.service   # Agnes Today Actions queue worker
```

只启动 `medical-pilot.service` 不算 Agnes 闭环完成：API 会排队，但没有 Worker 消费。

## 服务端环境

`/etc/medicalchannelai/pilot.env`：

```text
MCAI_CANONICAL_ORIGIN=https://<pilot-domain>
MCAI_AGNES_API_KEY=<server-only-key>
# 只有确有需要才覆盖；仍受客户端 allowlist 约束
# MCAI_AGNES_BASE_URL=https://api.agnes.ai/api/v1
```

`MCAI_AGNES_API_KEY` 只能存在服务端环境。禁止进入 H5、SQLite 客户画像、GitHub、日志、URL 或浏览器 LocalStorage。

## systemd

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

## 创建一个可直接填写资料的客户

不再手写完整 profile JSON。管理员执行：

```bash
cd /srv/medical/app
sudo -u medicalai python3 -m tools.medical_pilot.pilot_admin \
  --db /srv/medical/data/pilot.sqlite \
  bootstrap-invite \
  --tenant tianjin-duokelong \
  --company '天津多克隆商贸' \
  --ttl 1800 \
  --login-url 'https://<pilot-domain>'
```

输出中的 `login_url` 只发给目标客户，不贴 GitHub / Issue / 日志。一次性邀请码用后失效。

登录成功默认进入 `/profile`，不是 `/today`。

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

Vercel Preview 只验证 H5 构建，不运行 Python API / systemd Agnes Worker。
