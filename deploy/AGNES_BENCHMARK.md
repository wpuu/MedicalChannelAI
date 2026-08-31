# Agnes 28-case Benchmark Runbook

Status: `READY_FOR_TARGET_HOST_EXECUTION / NOT_YET_EXECUTED`

本步骤用于真实目标主机验证 `agnes-2.5-flash` 的 28-case 医疗渠道分类能力。它不是客户请求链路，也不是自动准入流程。

## 固定原则

- 12 条粗分类 + 16 条产品 taxonomy = 28 条固定 case；
- 不修改 benchmark 题目或门槛来追求通过；
- 每个 provider start 都必须先取得共享 `Agnes global lease`；
- 单 case provider retry 固定为 0；失败后不在同一 lease 内重试；
- 仅允许官方 allowlist `/v1` endpoint；
- 模型固定 `agnes-2.5-flash`；
- Key 仅来自 `/etc/medicalchannelai/pilot.env` 的 `MCAI_AGNES_API_KEY`；
- benchmark 只允许在维护窗口执行，API/Worker 必须先停止，业务 Agnes queue 必须为空；
- 即使 28-case 全 PASS，也**不得自动修改** `product_classifier_registry.v0.1.json`，不得自动把 classifier 从 `BENCHMARK_PENDING` 改为 `VALIDATED`。

## 1. 安装一次性 unit

```bash
cd /srv/medical/app
sudo cp deploy/medical-agnes-benchmark.service /etc/systemd/system/
sudo systemctl daemon-reload
```

这个 unit 没有 `[Install]`，不要 enable；只允许管理员手工 start。

## 2. 执行前停止客户服务

```bash
sudo systemctl stop medical-pilot.service
sudo systemctl stop medical-agnes-worker.service
sudo systemctl is-active medical-pilot.service
sudo systemctl is-active medical-agnes-worker.service
```

两者都必须不是 `active`。unit 还会再次 fail-closed 检查；任一仍 active 都不会开始 benchmark。

## 3. 确认旧结果不存在

默认私有结果文件：

```text
/srv/medical/data/agnes-benchmark-result-v0.1.json
```

执行器拒绝覆盖已有结果。若要重新跑，管理员必须先人工归档旧文件并记录原因，不能静默覆盖历史结果。

## 4. 运行

```bash
sudo systemctl start medical-agnes-benchmark.service
sudo systemctl status medical-agnes-benchmark.service --no-pager
sudo journalctl -u medical-agnes-benchmark.service -n 80 --no-pager
```

正常完整执行会产生 28 次真实 Agnes provider start，受同一共享 lease 限制，至少遵守生产策略的启动间隔/RPM/in-flight 约束。

## 5. 只接受安全结果

结果文件权限应为：

```text
0600
```

PASS 至少要求：

```text
status=PASS
total_case_count=28
completed_case_count=28
provider_start_count=28
every_provider_start_requires_global_lease=true
provider_retries_per_case=0
business_queue_quiescent_required=true
maintenance_window_confirmed=true
classifier_registry_modified=false
automatic_classifier_admission_allowed=false
automatic_classifier_admission_performed=false
admission_recommendation=ELIGIBLE_FOR_MANUAL_ADMISSION_REVIEW
```

`ELIGIBLE_FOR_MANUAL_ADMISSION_REVIEW` 只表示可以进入人工准入审核，不等于已经准入。

## 6. FAIL 的处理

任一 case/provider/contract/queue/lease 失败时：

- 保持 classifier `BENCHMARK_PENDING`；
- 不自动重跑；
- 不自动切换 Agnes 地区 endpoint；
- 不自动修改 taxonomy/题目/通过阈值；
- 先审查失败类别，再决定是否在新的维护窗口完整重跑。

## 7. 恢复客户服务

benchmark 完成并确认结果文件落盘后：

```bash
sudo systemctl start medical-pilot.service
sudo systemctl start medical-agnes-worker.service
```

随后按正常运行手册检查 health 和业务 queue。

## 当前项目事实

截至本文加入仓库时：

```text
agnes_benchmark_cases=28
agnes_benchmark_executed=false
classifier=BENCHMARK_PENDING
production_ready=false
```

不要把“执行器准备完成”写成“Agnes benchmark 已通过”。
