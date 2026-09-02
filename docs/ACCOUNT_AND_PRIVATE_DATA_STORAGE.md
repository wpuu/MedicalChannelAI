# 账号与个人/客户私有数据存储方案

更新时间：2026-09-02

## 1. 结论

MedicalChannelAI 的真实 Pilot 账号与客户私有数据不再以浏览器 `localStorage` 作为主存储。

目标架构：

1. 浏览器 / 手机 H5：只持有 HttpOnly 登录 Cookie，以及必要的短期页面状态；
2. 同源 `/api/*`：负责认证、数据校验、权限隔离和最小化读取；
3. 私有 PostgreSQL：保存账号、会话、客户自填资源、跟进和推荐反馈；
4. 公开采购事实：继续来自 VERIFIED 公开事实快照，与私有客户数据分开存储；
5. AI：Pilot 浏览器只提交 `opportunity_id`，服务端按当前登录用户读取与该商机相关的最小私有资料后再调用 AI。

当前代码已经完成上述接口和数据表，但真实数据库实例尚未绑定到部署环境。未配置 `DATABASE_URL` / `POSTGRES_URL` 时，账号接口必须 fail-closed，不能退回伪登录或匿名私有数据模式。

## 2. 默认不采集的信息

Pilot 注册默认不要求：

- 手机号
- 邮箱
- 真实姓名
- 身份证号
- 家庭地址

注册只需要：

- 一次性邀请码
- 用户自选账号名
- 用户自设密码

密码不保存明文，只保存随机盐 + scrypt 派生哈希。

## 3. 私有 PostgreSQL 数据表

### 账号与权限

- `private_organizations`
- `private_users`
- `private_pilot_invites`
- `private_sessions`

### 用户主动填写的业务资源

- `private_product_capabilities`
- `private_hospital_relationships`
- `private_user_preferences`

### 用户行为和业务流程

- `private_followups`
- `private_followup_events`
- `private_recommendation_feedback`

所有业务私有数据都至少按 `user_id` 隔离；需要组织范围的数据同时带 `organization_id`。

## 4. 登录和会话

- 登录 Cookie：`HttpOnly`、`SameSite=Lax`，HTTPS/Vercel 下使用 `Secure`；
- 浏览器 JavaScript 不能直接读取 session token；
- 数据库只保存 session token 的 SHA-256 哈希，不保存原 token；
- 默认会话有效期 30 天；
- 退出时删除当前 session 并清 Cookie。

## 5. 邀请码

真实邀请码在数据库中只保存 SHA-256 哈希。

首批 Pilot 可通过服务端环境变量 `PILOT_INVITE_CODES` 配置一次性启动邀请码；成功注册后数据库原子标记为已使用，避免同一邀请码并发创建多个账号。

邀请码不要写入：

- GitHub 源码
- Vite `VITE_*` 前端变量
- 浏览器 localStorage
- 前端日志

## 6. 公开事实与私有数据隔离

以下属于公开事实层：

- 医院 / 采购单位
- 官方项目标题
- 官方发布时间
- 官方报名/投标截止时间
- 官方公开预算
- 官方产品/设备明细
- 官方公开联系人
- 官方证据 URL

以下属于客户私有层：

- “我能做哪些产品”
- “我与哪些医院/科室有关系”
- “我能否临时找厂家/合作渠道/做租赁”
- 我的跟进状态、备注、提醒
- 推荐反馈

私有关系不能反写成公开事实，也不能因为医院官方联系人存在就推断用户与该医院有关系。

## 7. AI 最小化原则

真实 Pilot 下：

1. 浏览器只发送当前 `opportunity_id`；
2. 服务端从 VERIFIED 快照取得该商机官方事实；
3. 服务端根据当前 HttpOnly 会话定位用户；
4. 只筛出与当前商机匹配的产品能力、医院/科室关系和必要合作能力；
5. 将最小化后的上下文交给 AI；
6. 浏览器提交的 `customer_context` 在 Pilot 模式直接拒绝。

这样可以避免客户端伪造私有画像，也避免每次把用户全部医院关系和全部产品资源发给 AI。

## 8. 旧 localStorage 数据迁移

公开试用阶段可能已有：

- 产品能力
- 医院关系
- 合作能力

注册/登录后不得自动上传。

页面只有检测到本机旧资料时才展示“导入本机试用资源到当前账号”。只有用户主动点击后才上传。

合并规则：

- 账号已有数据优先；
- 相同产品关键词不被旧本机数据覆盖；
- 相同医院 + 科室关系不被旧本机数据覆盖；
- 账号已经回答过的合作能力不被旧值覆盖；
- 导入成功后不自动删除本机副本；
- 用户可单独选择“仅清除本机副本”。

## 9. 部署需要的服务端环境变量

真实 Pilot 至少需要：

- `DATABASE_URL` 或 `POSTGRES_URL`
- `PILOT_INVITE_CODES`
- `PILOT_PRIVATE_ACCOUNTS_ENABLED=1`

前端 Pilot 构建需要：

- `VITE_BUILD_MODE=pilot`
- `VITE_API_BASE_URL=/api`

数据库连接串、邀请码、AI Key 等敏感值只能放服务端环境变量，禁止使用 `VITE_*` 暴露到浏览器。

## 10. 数据库物理位置

代码层已经固定为标准 PostgreSQL 接口，但当前尚未绑定真实数据库实例，因此目前不能声称个人数据已经存放在 Neon、Vercel、阿里云、腾讯云或任何具体地区。

在真实外部 Pilot 前，需要明确选择数据库供应商和数据区域，再配置 `DATABASE_URL`。MedicalChannelAI 是中国市场项目，正式客户使用前应单独评估数据地域、隐私政策、跨境传输以及供应商运维条件；内部开发/测试数据库与正式客户数据库应分开。
