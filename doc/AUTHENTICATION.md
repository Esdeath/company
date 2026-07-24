# 管理员与站点用户认证

## 两套身份边界

系统保留一个环境变量管理员，同时提供经过邮箱验证的普通站点用户。管理员与普通用户使用不同的路由、数据表、Cookie、会话和 CSRF 令牌，不能交叉使用。公开公司、资料、内容与已发布评论无需登录；管理写入要求管理员身份，评论和账户写入要求普通用户身份。

生产 Cookie 都使用 `HttpOnly; Secure; SameSite=Strict; Path=/`：管理员 Cookie 是 `__Host-company-admin-session`，普通用户 Cookie 是 `__Host-company-user-session`。数据库只保存随机会话令牌的 SHA-256，原始令牌只存在浏览器 Cookie 中。两个前端都只在内存保存对应会话返回的 CSRF 令牌，并在 POST、PATCH、DELETE 请求中发送 `X-CSRF-Token`。

## 管理员登录

1. 管理端请求 `GET /api/v1/auth/session`，未登录时取得十分钟有效的一次性挑战。
2. 登录把用户名和密码放在 JSON 中，把挑战放在 `X-CSRF-Token`；挑战无论成功或失败都只能消费一次。
3. API 用 Argon2 校验密码，创建十二小时服务器会话，并设置管理员 Cookie。
4. 会话记录管理员密码哈希的指纹，更换哈希会使旧会话失效；退出同时删除数据库会话和 Cookie。

生产 Nginx 分别限制管理员登录与匿名会话挑战的每 IP 请求频率。

## 普通用户流程

普通用户先从 `GET /api/v1/user-auth/session` 取得十分钟有效的一次性挑战。注册、登录、验证邮箱和密码重置提交该挑战；注册邮件链接有效 24 小时，密码重置链接有效 30 分钟。验证或登录成功后创建最长 30 天的服务器会话。暂停、删除或修改密码会撤销不再有效的会话。

注册、登录、重发验证与密码重置同时受宿主机 Nginx 的每 IP 限流和 API 的账户主体限流保护。接口对重复邮箱和不存在的重置邮箱返回通用消息，日志不得记录密码、Cookie、CSRF 或链接令牌。

## 配置与开关

```dotenv
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH='$argon2id$...'
SESSION_COOKIE_SECURE=true
SESSION_LIFETIME_SECONDS=43200
USER_SESSION_LIFETIME_SECONDS=2592000
USER_TOKEN_SIGNING_KEY=<至少 32 字节的持久随机密钥>
USER_REGISTRATION_ENABLED=false
COMMENT_WRITES_ENABLED=true
```

运行 `make admin-password-hash` 交互式生成管理员哈希。哈希必须保留外层单引号，避免 Docker Compose 展开其中的 `$`。本地 HTTP 开发设置 `SESSION_COOKIE_SECURE=false`；生产只能设为 `true`。

`USER_TOKEN_SIGNING_KEY` 用于生成可重建的 HMAC 邮件链接令牌，不能轮换或输出到日志，否则未使用的验证、重置和退订链接会立即失效。部署脚本仅在首次缺失时在 ECS 生成并保存该密钥。`USER_REGISTRATION_ENABLED=false` 关闭新注册但不影响已有用户登录；`COMMENT_WRITES_ENABLED=false` 使评论区只读。

## 安全边界

- 不在 `localStorage` 或 `sessionStorage` 保存任何会话令牌。
- 认证与 CSRF 失败分别返回 401 和 403；账号、IP 限流返回 429。
- HTTPS Nginx 是唯一公网入口；8000、8080 和 5432 不开放公网。
- 当前没有二次验证或自动内容审核。若以后横向扩容 Nginx，需把每 IP 限流升级为共享外部机制。
