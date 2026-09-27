# qd.je 零成本入口

任务：MCAI-QDJE-ZEROCOST-003

用途：让 `medicalai.qd.je` 在不使用常驻 VPS 的情况下继续可访问。

本目录只包含一个极薄的 Firebase Hosting 静态入口：

- 根路径 `/` 跳转到 `https://medicalchannelai.vercel.app/today`；
- 其他路径保留原 pathname / query / hash 后跳转到 Vercel Production；
- 不保存用户数据；
- 不调用模型；
- 不包含 API Key；
- 不承担 MedicalChannelAI 业务逻辑。

切换 DNS 前必须先在 Firebase Hosting 中完成自定义域名 ownership / SSL 准备。Firebase 给出的 TXT/A 记录是唯一权威配置，不在仓库中硬编码。

切换成功并验证 HTTPS 后，才允许释放 `35.211.124.40` 对应的 GCP 资源。
