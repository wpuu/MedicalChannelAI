# MedicalChannelAI 当前状态

日期：2026-08-31  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`DETERMINISTIC_AND_REAL_PUBLIC_BOOTSTRAP_PASS / REAL_AGNES_AND_PILOT_HOST_SMOKE_PENDING`  
生产就绪：**false**  
Draft PR：**#1（保持 Draft，不合并）**

## 当前可信验证基线

最新干净验证提交：`63d47aa1a0311a74a02908456733ca41679b559c`  
Vercel deployment：`dpl_DK3P2jgaLHqfkGAFV6verUpHj9ZG` → **READY**

同一提交实际执行：

- `478` 个 Python unittest → **OK**；
- `npx tsc --noEmit` → **PASS**；
- Vite production build → **PASS**；
- `1887` modules transformed；
- `dist/index.html` 约 `413.58 KiB`，gzip `127.17 KiB`。

GitHub Actions 仍存在 runner 未分配问题，因此当前可信执行门使用 Vercel Preview，而不是把 GitHub Actions 的 runner failure 当代码失败。

## 当前规模

- 7 个运行时 P0 Source：4 `IMPLEMENTED`、3 `PARTIAL_IMPLEMENTATION`；
- 自动 listing discovery：2/7 ready；
- 50 条 VERIFIED 天津商机 regression fixtures；
- 15 条 Institution Evidence；
- 41 份 Schema/合同；
- 88 个 deterministic test modules；
- 478 个实际执行 unittest cases；
- 真实医疗附件 binary capture：**0**；
- Agnes benchmark：28 case，尚未真实执行；
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`。

## 当前商务 Demo

Vercel verified public-data Demo：

```text
https://medicalchannelai.vercel.app
```

该 Demo 展示真实公开项目快照，但客户资源/画像为明确的演示数据；它不是老杨的真实账号，也没有启用真实 Agnes provider。

## 真实 Pilot 已具备的产品链

- 邀请制注册、账号状态、30天 server-side opaque Session；
- `/profile` 客户画像编辑；
- Today Top5 + 详情；
- 客户产品能力以 controlled taxonomy ID 作为稳定匹配键；
- profile 保存后重新计算 Today 并按需排 Agnes；
- 画像达到候选条件后保存直接进入 `/today`；
- tenant/profile private follow-up；
- 到期站内提醒；
- `/followed` 长期跟进；
- grounded on-demand outreach；
- VERIFIED public facts 与 customer-confirmed private context 分离；
- 浏览器不能自报可信 tenant/profile；
- canonical Host/Origin API boundary；
- 单机 SQLite + Caddy + systemd 部署脚手架；
- Agnes persistent queue/worker + shared global lease。

仍不得标记 production-ready，因为真实 Pilot 主机、真实 Agnes provider、真实附件和外部提醒交付等还没有完成最终 smoke。

## 真实天津公开数据 bootstrap

Manifest：`deploy/tianjin-pilot-bootstrap-urls-2026-08-30.json`  
Importer：`python3 -m tools.medical_pilot.pilot_live_seed`

隔离 Vercel live verification 已真实访问5条注册官方 URL：

- input=5；
- success=5；
- failure=0；
- 项目编号在持久化前与 manifest expected code 核对；
- 不 seed 客户关系；
- 不 seed 预写 Agnes 结论。

真实验证 deployment：`dpl_5TnA7PKNWtJitBUak1m7CbBnExE5`。

## CCGP 采购需求 grounding 已修复并真实验证

新增 `tools/medical_pilot/ccgp_procurement_demand.py`，只从明确 `包号 + 采购需求` 表格的合法包号行生成 VERIFIED `product_item` facts；资格条件、政策说明、联系人等正文不会进入 taxonomy。

修复后的真实 live bootstrap 中，`XCSD-2026-C-181 / 病原微生物能力提升相关设备购置` 已得到：

- `LAB_NGS_SEQUENCER`
- `LAB_AUTOMATED_LIBRARY_PREP`
- `LAB_METAGENOMICS_ANALYSIS`
- `LAB_MICROBIAL_MASS_SPECTROMETRY`
- `LAB_BIOINFORMATICS_COMPUTE_APPLIANCE`

这些 ID 已同步暴露到 `/profile` 产品能力选择。泰达医院 DR 仍正确得到 `MEDICAL_IMAGING_DR`；其余信息不足项目继续保持空标签，不硬猜。

## 真实附件状态：仍未通过

已实现 bounded live attachment probe：

```text
tools/medical_pilot/attachment_live_probe.py
```

限制 HTTPS、天津财政官方 host、`method=downEnId`、DOCX/XLSX、最大32MiB、MIME、magic、SHA-256、本地 OOXML parser。

Vercel IAD 两次真实请求分别在约20秒和60秒发生 read timeout，均未拿到响应 bytes。因此当前必须保持：

- real attachment bytes = 0；
- MIME/size/SHA-256 = 未观察；
- real OOXML parser = 未在该真实附件上通过。

下一次应从中国附近的真实 Pilot 主机或更适合访问天津政府站点的网络执行。

## Agnes 当前真相

已完成：

- server-only provider architecture；
- `agnes-2.5-flash` contract；
- queue / scheduler / terminal result；
- shared global lease；
- Today worker；
- grounded outreach；
- deterministic contract tests；
- 隔离 provider smoke CLI：`python3 -m tools.medical_pilot.agnes_provider_smoke`。

该 smoke 使用固定合成 grounded input + 临时 SQLite lease，不读取老杨资料；仍通过正式 global lease 和 `validate_model_decision`，不会绕过生产边界。

尚未完成：

- `MCAI_AGNES_API_KEY` 在真实 Pilot 执行环境中的最终配置；
- **真实 authenticated Agnes provider smoke**；
- 老杨真实 profile → queue → worker → `READY` Top5 的端到端验收。

因此不能声称“真实 Agnes 已跑通”。

## Discovery

自动 listing discovery 仍只有 2/7 ready：

1. `tjmugh_procurement`
2. `tj_first_central_hospital_procurement`

其余5个继续 fail-closed：不猜 classId/pagination，不绕 CAPTCHA，不为自动化覆盖率制造虚假成功。

## 下一步优先级

1. 在中国附近的 Pilot 主机执行真实附件 probe，拿到 bytes/MIME/SHA/parser 证据；
2. 配置 server-only `MCAI_AGNES_API_KEY`，执行 `python3 -m tools.medical_pilot.agnes_provider_smoke`；
3. provider smoke PASS 后启动真实 API + Agnes Worker；
4. 创建老杨 INVITED 账号并发送一次性注册链接；
5. 老杨填产品能力、厂家/渠道/租赁能力和确认医院关系；
6. 验证保存后 Agnes 任务排队、worker 运行、Today Top5 从 `AWAITING_MODEL` 进入 `READY`；
7. 再做 authenticated follow-up/reminder/followed/outreach、backup/restore 和大陆/微信实际访问验收。
