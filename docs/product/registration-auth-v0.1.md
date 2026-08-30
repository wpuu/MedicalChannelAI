# MedicalChannelAI 注册 / 登录策略 v0.1

状态：FROZEN_FOR_TIANJIN_PILOT

## 结论

天津 Pilot 不开放匿名自助注册。采用 **邀请注册制**：

1. 管理员创建一个客户账号与空白客户画像；
2. 系统生成一次性高熵邀请链接；
3. 客户打开链接完成首次注册/激活；
4. 浏览器获得 HttpOnly opaque Session；
5. 首次进入 `/profile` 填写医院关系、产品能力、品牌/厂家资源、合作/租赁能力、金额与阶段偏好；
6. 保存画像后后端立即重算 Today Actions，并将需要模型判断的最终候选送入 Agnes 队列；
7. 客户以后直接使用同一账号，默认 Session 最长 30 天；
8. 换设备或 Session 到期时，管理员给同一账号重新发一次性登录链接，不新建客户画像。

## 为什么 Pilot 不开放公开注册

- 防止垃圾租户和脚本批量注册消耗 Agnes；
- 不需要提前接短信、邮件验证码、密码找回和反滥用系统；
- 当前客户数量很少，定向邀请人工成本极低；
- 客户画像、跟进、提醒均为私有业务数据，账号创建应受控；
- 等真实付费和获客路径验证后，再决定正式身份提供方和注册渠道。

## 账号状态

- `INVITED`：账号已创建、尚未首次激活；
- `ACTIVE`：已完成邀请注册，可使用；
- `DISABLED`：管理员停用，所有业务 API 拒绝该账号。

账号与 `tenant_id + profile_id` 在 Pilot 阶段 1:1 绑定。

## Session

- Cookie：`__Host-mcai_session`；
- 随机 opaque token；
- 数据库只保存 SHA-256；
- `Secure + HttpOnly + SameSite=Strict`；
- 默认最长 30 天；
- 浏览器永远不接触 tenant/profile 编码凭据；
- 账号停用时同时撤销该账号全部 Session；
- 账号恢复后旧 Cookie 不复活，必须重新登录。

## 邀请

邀请代码：

- 一次性；
- 数据库只保存 SHA-256；
- 默认 30 分钟过期；
- 只绑定服务器已知 tenant/profile；
- URL 使用 fragment：`/login#code=...`，避免邀请码被正常 HTTP Referer/请求路径发送；
- 成功兑换后立即作废。

## 管理员最低操作

首次创建客户：

```bash
python3 -m tools.medical_pilot.pilot_admin \
  --db /srv/medical/data/pilot.sqlite \
  bootstrap-invite \
  --company "天津试用客户" \
  --login-url "https://<pilot-domain>"
```

`--tenant` 可省略，由系统生成。

Session 到期 / 换设备：

```bash
python3 -m tools.medical_pilot.pilot_admin \
  --db /srv/medical/data/pilot.sqlite \
  invite --tenant <tenant_id> --profile <profile_id> \
  --login-url "https://<pilot-domain>"
```

停用：

```bash
python3 -m tools.medical_pilot.pilot_admin \
  --db /srv/medical/data/pilot.sqlite \
  account-disable --tenant <tenant_id> --profile <profile_id>
```

停用必须同时撤销该账号全部当前 Session。

恢复：

```bash
python3 -m tools.medical_pilot.pilot_admin \
  --db /srv/medical/data/pilot.sqlite \
  account-enable --tenant <tenant_id> --profile <profile_id>
```

恢复后仍需重新执行 `invite`，不允许旧 Cookie 自动复活。

## 正式收费版再增加

以下内容不属于天津 Pilot 的上线前提：

- 公开“申请试用”表单；
- 手机号/邮箱验证；
- 密码或 Passkey；
- 多用户加入同一企业 tenant；
- Owner/Admin/Member RBAC；
- 自助密码找回；
- 付费后自动激活；
- 邀请团队成员。

正式版建议采用：

`申请试用/付款 -> 审核或自动风控 -> 创建 tenant -> 用户身份验证 -> ACTIVE -> Agnes 权限/额度`

即便未来开放自助申请，**注册成功也不等于可以无限调用 Agnes**；模型额度和租户权限仍必须由服务端控制。
