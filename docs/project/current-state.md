# MedicalChannelAI 当前状态

日期：2026-08-31  
分支：`dev/tianjin-pilot-v0.1`  
阶段：`DETERMINISTIC + REAL_PUBLIC_BOOTSTRAP PASS / HOST_ACCEPTANCE READY / REAL_HOST EXECUTION PENDING`  
生产就绪：**false**  
Draft PR：**#1（保持 Draft，不合并）**

## 当前可信验证基线

代码门禁证据：`7c40802019b280d8c6af6c7f543908e8a8ea5fd3`  
Vercel deployment：`dpl_2PL9asnHRPwrSDQ6PZdS12R96kv6` → **READY**

同一提交实际执行：

- **491 个 Python unittest → OK**；
- `npx tsc --noEmit` → PASS；
- Vite production build → PASS；
- 1887 modules transformed；
- `dist/index.html` 约 413.58 KiB / gzip 127.17 KiB。

GitHub Actions 仍存在 runner 未分配问题，因此开发分支继续使用 Vercel Preview 作为可信执行门。

本轮曾出现一轮 491-case 的单一失败：systemd unit 注释中出现了字符串 `[Install]`，触发了“acceptance unit 不得可安装”的字符串测试。只修改注释措辞、未放宽断言后，491 cases 全部通过。

## 当前规模

- 7 个运行时 P0 Source：4 IMPLEMENTED、3 PARTIAL_IMPLEMENTATION；
- 自动 listing discovery：2/7 ready；
- 50 条 VERIFIED 天津商机 regression fixtures；
- 15 条 Institution Evidence；
- 41 份 Schema/合同；
- **91 个 deterministic test modules**；
- **491 个实际执行 unittest cases**；
- 真实医疗附件 binary capture：0；
- Agnes benchmark：28 case，尚未真实执行；
- Coverage=`PARTIAL / NOT_EXHAUSTIVE`。

## 当前商务 Demo

```text
https://medicalchannelai.vercel.app
```

公开采购事实/官方链接是真实的；客户画像资源为明确演示数据；它不是老杨真实账号，也不是实时 Agnes。

## 真实公开数据链

5条冻结官方天津项目已经在隔离 live 环境真实执行：

```text
input=5
success=5
failure=0
```

CCGP `采购需求` 表格已经进入 VERIFIED `product_item` grounding。`XCSD-2026-C-181 / 病原微生物能力提升相关设备购置` 已真实得到：

- `LAB_NGS_SEQUENCER`
- `LAB_AUTOMATED_LIBRARY_PREP`
- `LAB_METAGENOMICS_ANALYSIS`
- `LAB_MICROBIAL_MASS_SPECTROMETRY`
- `LAB_BIOINFORMATICS_COMPUTE_APPLIANCE`

这些 controlled taxonomy ID 已同步进入 `/profile` 产品能力选择。

## 真实附件状态

`XCSD-2026-C-181项目需求书.docx` 的天津财政官方下载 URL 已被冻结到：

```text
deploy/pilot-host-acceptance-v0.1.json
```

Vercel IAD 两次真实下载分别约20秒、60秒 read timeout，因此当前继续保持：

```text
real attachment bytes = 0
MIME/size/SHA-256 = 未观察
real OOXML parser = 未在该真实附件上 PASS
```

不把“官方 URL 已确认”解释成“附件 binary 已验证”。

## 真实 Agnes 状态

已经具备：

- server-only `MCAI_AGNES_API_KEY` 架构；
- `agnes-2.5-flash` constrained contract；
- persistent queue / Worker / terminal result；
- shared global lease；
- grounded Today Actions / outreach；
- 独立 synthetic provider smoke。

但真实 authenticated Agnes provider 尚未在目标 Pilot 主机 PASS，因此不能声称“真实 Agnes 已跑通”。

## 新增：统一真实 Pilot 主机验收

核心文件：

```text
tools/medical_pilot/pilot_host_preflight.py
tools/medical_pilot/pilot_host_acceptance.py
deploy/pilot-host-acceptance-v0.1.json
deploy/medical-pilot-acceptance.service
deploy/PILOT_HOST_ACCEPTANCE.md
```

API 与 Worker systemd unit 现在都：

1. 强制要求 `/etc/medicalchannelai/pilot.env` 存在，不再把 EnvironmentFile 设为 optional；
2. 在正式 `ExecStart` 前执行 `pilot_host_preflight`；
3. API 检查 canonical HTTPS origin + DB 路径；
4. Worker 检查 Agnes Key + allowlisted official base URL + DB 路径；
5. 失败时 fail-closed，不启动服务。

统一 acceptance 通过一个 manual oneshot：

```bash
sudo systemctl start medical-pilot-acceptance.service
sudo journalctl -u medical-pilot-acceptance.service -n 50 --no-pager
```

它会：

```text
真实主机配置/DB路径 preflight
→ 临时 SQLite 5条官方 bootstrap（必须5/5）
→ 真实天津附件 bytes/MIME/SHA/parser
→ 合成 grounded input 的真实 Agnes authenticated contract smoke
```

四项全部 PASS 才返回 overall `status=PASS`。

关键安全边界：

- 只检查真实 `/srv/medical/data/pilot.sqlite` 路径/权限，**不写生产 DB**；
- bootstrap 使用临时 SQLite；
- Agnes smoke 使用临时 SQLite lease；
- 不读取老杨/真实客户资料；
- 不打印 Key、provider body、完整 model input、附件正文。

## 真实服务器后的固定顺序

1. 部署代码/H5、创建 `medicalai` 用户和 `/srv/medical/data`；
2. 创建 root-only `/etc/medicalchannelai/pilot.env`；
3. 安装三个 systemd unit；
4. **先运行 `medical-pilot-acceptance.service`，overall PASS 才继续**；
5. 再把5条官方项目正式导入 `/srv/medical/data/pilot.sqlite`；
6. 启动 `medical-pilot.service` + `medical-agnes-worker.service`；
7. 验证本机 health、真实 queue → Agnes → READY；
8. 之后才创建老杨 INVITED 账号并发送一次性注册链接；
9. 完成 authenticated followup/reminder/followed/outreach、backup/restore、大陆/微信访问验收后，才评估 production_ready / merge。

## 仍然不能宣称

当前继续保持：

```text
production_ready=false
real_authenticated_agnes_provider_pass=false
real_attachment_binary_capture_count=0
PR #1 = Draft / do not merge
```
