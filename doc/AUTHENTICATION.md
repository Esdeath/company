# 管理员认证、会话与 CSRF

## 范围

当前系统只有一个管理员。用户名和 Argon2 密码哈希由环境变量提供，不建立管理员用户表，也不支持注册、找回密码或角色权限。公开读取接口无需登录；创建公司、上传、重命名和删除必须同时通过会话与 CSRF 校验。

## 登录流程

1. 管理端请求 `GET /api/v1/auth/session`。
2. 未登录时，API 创建十分钟有效的一次性登录挑战，只把挑战的 SHA-256 写入 PostgreSQL，并把原始挑战作为 `csrf_token` 返回。
3. 登录请求把用户名和密码放在 JSON 中，把挑战放在 `X-CSRF-Token`。挑战不论登录成功或失败都只能消费一次。
4. API 用 Argon2 校验密码，创建十二小时服务器会话，并设置 `HttpOnly; Secure; SameSite=Strict; Path=/` Cookie。
5. 数据库只保存会话令牌的 SHA-256；原始会话令牌只存在浏览器 Cookie 中。会话还记录管理员密码哈希的指纹，修改密码哈希会自动使旧会话失效。

登录成功后，API 返回与会话绑定的 CSRF 令牌。前端只在内存保存它，并自动附加到所有 POST、PATCH 和 DELETE 请求。退出会删除数据库会话并清除 Cookie；过期会话不能恢复。生产 Nginx 把登录接口限制为每个 IP 每分钟五次请求，也限制匿名会话挑战的申请频率，并允许小幅突发。

## 配置

```dotenv
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH='$argon2id$...'
SESSION_COOKIE_SECURE=true
SESSION_LIFETIME_SECONDS=43200
```

运行 `make admin-password-hash` 交互式生成哈希。必须保留哈希外层单引号，避免 Docker Compose 展开其中的 `$`。本地 HTTP 开发设置 `SESSION_COOKIE_SECURE=false`；生产只能设为 `true`。

## 安全边界

- 不在 `localStorage` 或 `sessionStorage` 保存会话令牌。
- 认证与 CSRF 失败分别返回 401 和 403，不泄露密码、哈希或内部异常。
- HTTPS Nginx 是唯一公网入口；8000、8080 和 5432 不开放公网。
- 当前没有二次验证、登录失败审计和分布式速率限制。若以后横向扩容 Nginx，需要把限速升级为共享外部机制。
