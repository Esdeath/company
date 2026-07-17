# 后端设计

## 职责与边界

本文定义生产目标；当前 `doc/prototype.html` 没有真实后端。FastAPI 是唯一能够修改生产内容文件和发布状态的服务。Nuxt 公开端与 Vue/Vite 管理端只通过 API 读取或发起受权操作，不能直接写内容目录或 PostgreSQL。

HTML 是网站唯一发布物。MD 不进入后端上传、解析、预览、API 或持久化流程。Skill 在网站外生成的 MD 只供审计和重新生成使用。

所有接口使用 `/api/v1` 前缀，JSON 字段使用 `snake_case`，时间使用带时区的 ISO 8601。列表使用游标分页。OpenAPI 是前后端契约来源。

## 内容模型

目标记录形状如下：

```json
{
  "id": "uuid",
  "company_name": "贵州茅台",
  "ticker": "600519",
  "market": "CN",
  "data_as_of": "2025-12-31",
  "title": "价值线企业快照版 — 贵州茅台 (600519.SH)",
  "html_path": "published/CN/600519/2025-12-31.html",
  "content_sha256": "64 lowercase hex characters",
  "status": "draft | published | withdrawn",
  "published_at": null
}
```

`html_path` 是内容根目录下的 POSIX 相对路径。API 不直接暴露该字段；公开响应把它转换为受控的稳定 HTML URL。`content_sha256` 保存文件字节的 SHA-256。`published_at` 在首次或最近一次发布时写入 ISO 8601 时间；草稿为 `null`。数据库另存 `version` 整数供乐观并发控制，不改变上述公开内容形状。

## HTML 校验

FastAPI 在导入、重新校验和发布前先执行静态校验。静态校验至少覆盖：

- 文件可读性、普通文件、非符号链接、路径不越界、`.html` 扩展名、`text/html` MIME、允许的大小和 UTF-8 编码。
- 完整文档结构，包括 doctype、`html`、charset、viewport、非空 `title`、`style` 与 `body`。
- 页面标题及公司名称、证券代码、市场和数据截止日元数据；标题必须与公司和代码相符。
- 远程资源禁令，包括 HTML 属性中的 HTTP(S) 或协议相对 URL、CSS `url()` 和 `@import`。
- 禁止 `script`、内嵌或嵌套 `iframe`、表单、提交动作、`meta refresh`、顶层导航和其他可执行导航能力。

文件不可读、MIME 或大小不合规、结构或安全校验失败时，FastAPI 返回错误，不签发预览地址，也不让浏览器或检查器探测该文件。静态校验为 `clean` 后，FastAPI 创建绑定 `record id`、`version`、`content_sha256` 与随机 `nonce` 的受控预览 URL。该 URL 要求管理员鉴权或检查器内部凭据，并返回 `X-Robots-Tag: noindex, nofollow` 与 `Cache-Control: no-store`。

权威加载门禁按以下顺序执行：

1. FastAPI 创建预览 URL 后触发内部任务，将记录状态设为 `html-checking`。
2. 可信 load-checker 通过内部认证通道取得同一 URL，先执行实际 `HEAD`，再用 headless Chromium 在 sandboxed iframe 中加载该 URL，并等待 `load`、`error` 或 `timeout`。
3. 只有可信 load-checker 能写权威 `passed` 或 `failed`。管理员客户端不得提交或决定 `passed`；它只能触发检查、单独显示本地预览状态，并轮询权威结果。
4. FastAPI 保存检查器结果及完成时间。文件、`version`、`content_sha256` 或 `nonce` 发生任何变化时，结果立即失效；下一次检查必须生成新 nonce。
5. 发布门禁同时要求静态校验为 `clean`，且当前版本、哈希和 nonce 对应的可信 load-check 为 `passed`。

可信检查的 `HEAD`、iframe 加载或等待失败时，检查器写 `failed`。管理端轮询到失败后移除本地预览 iframe、显示错误并继续阻断发布。警告可以保留草稿，但发布请求必须携带明确确认。每次发布都重新计算 SHA-256，并核对导入时的哈希和版本。

## 状态机

状态只允许：

```text
draft（草稿） → published（已发布） → withdrawn（已撤回）
       ↑                  │                    │
       └── 可删除草稿     └── 撤回             └── 重新校验后可再次发布
```

公开查询只读取 `published`。`draft` 和 `withdrawn` 对公开 API 均表现为 404。发布要求草稿或已撤回记录通过最新校验；撤回只接受已发布记录。删除只接受符合保留策略且从未发布的草稿，不能删除已发布记录。

重复键为 `(market, ticker, data_as_of)`。同一版本默认返回冲突；管理员只能显式替换未发布草稿，不能覆盖已发布文件。

## 文件存储

上传先写入受控临时目录，校验通过后按已验证元数据计算目标路径并原子移动。最终路径不使用原始文件名。生产目录至少分为 `drafts/` 与 `published/`；撤回文件离开公开目录并保留可审计副本。

文件系统保存 HTML 字节，PostgreSQL 不保存 HTML 正文。数据库只保存索引所需的相对路径和 SHA-256。服务不得接受任意绝对路径、符号链接、NUL、路径穿越或越界扫描。扫描只遍历配置根目录内的普通 `.html` 文件，并限制单次文件数量和总大小。

## PostgreSQL 索引

PostgreSQL 保存内容元数据、相对路径、SHA-256、状态、乐观锁版本、管理员账号、会话和审计记录，但不保存 HTML 正文。核心表为：

- `snapshot_index`：目标记录字段、`version`、校验计数、导入/更新/撤回时间。
- `snapshot_index` 的门禁字段：静态校验状态、load-check 状态及其绑定的版本、哈希、nonce、检查任务和完成时间。
- `admin_users`：规范化用户名、Argon2id 密码哈希和启用状态。
- `admin_sessions`：Session 哈希、CSRF 哈希、过期与撤销时间。
- `audit_logs`：操作者、目标、动作、请求标识、详情和时间。

公开索引只覆盖已发布状态，并按市场、数据截止日和发布时间排序；公司版本索引按市场、代码和日期排序。公司名包含搜索使用 `pg_trgm`，证券代码使用 B-tree 精确或前缀查询。会话过期和审计目标/时间分别建立索引。

## 认证与会话

管理端使用以下服务端 Session API：

```http
POST /api/v1/auth/login
GET  /api/v1/auth/me
POST /api/v1/auth/logout
POST /api/v1/auth/change-password
```

`POST /api/v1/auth/login` 发生在 Session 创建之前，所以登录请求不要求 Session CSRF Token。该接口仅接受 `application/json`；其他 Content-Type 返回 415。FastAPI 先校验请求 `Origin`，Origin 缺失时校验 `Referer`，两者都缺失或不与站点同源时返回 403，并且不验证用户名和密码。

- FastAPI 先执行登录限流；凭据失败时返回统一提示并写失败审计，不透露用户名是否存在。
- 登录成功后创建或轮换 Session，设置 `HttpOnly; Secure; SameSite=Strict` Session Cookie，并返回管理员基本信息及后续请求使用的 CSRF Token。数据库只保存 Session 和 CSRF 哈希，不保存原文。
- 当前管理员接口返回 Session 对应的管理员信息，不返回 Session ID 或哈希。
- `logout`、`change-password` 和所有非 GET 管理请求必须校验 Session CSRF Token。退出销毁服务端 Session 并用过期 Cookie 清除浏览器会话；改密还要校验当前密码，让其他 Session 全部失效，并轮换当前 Session。
- 默认闲置 12 小时失效，绝对有效期最长 7 天。
- 用户名存为规范化小写，密码使用 Argon2id。首个管理员由 CLI 初始化，不提供公开注册。
- 审计与服务日志不得保存明文密码、完整 Cookie 或完整 IP。

首版不提供公开 API Token。受保护接口在 Session 无效时返回 401，在 CSRF 或权限检查失败时返回 403。

## 公开 API

公开 API 只返回已发布记录：

```http
GET /api/v1/public/snapshots
GET /api/v1/public/snapshots/{market}/{ticker}
GET /api/v1/public/snapshots/{market}/{ticker}/{data_as_of}
```

列表支持 `q`、`market`、`sort`、`cursor`、`limit` 和 `latest_only`，返回 `items`、`next_cursor` 与 `previous_cursor`。详情返回元数据和受控的 `html_url`，例如 `/snapshots/CN/600519/2025-12-31.html`。API 不返回 HTML 正文、任意文件系统路径、草稿详情或已撤回详情。

无日期路由返回该公司最新已发布版本。不存在、未发布或已撤回记录统一返回 404。查询参数错误返回结构化 422，不泄露数据库或文件布局。

## 管理 API

管理接口支持以下目标操作：

```http
GET    /api/v1/admin/snapshots
POST   /api/v1/admin/snapshots/import
POST   /api/v1/admin/snapshots/scan
GET    /api/v1/admin/snapshots/{id}
POST   /api/v1/admin/snapshots/{id}/validate
GET    /api/v1/admin/snapshots/{id}/preview
POST   /api/v1/admin/snapshots/{id}/load-check
GET    /api/v1/admin/snapshots/{id}/load-check
POST   /api/v1/admin/snapshots/{id}/publish
POST   /api/v1/admin/snapshots/{id}/withdraw
DELETE /api/v1/admin/snapshots/{id}
```

导入只接受单个 `.html` 和 `text/html`；扫描只处理配置目录中的 `.html`。详情返回元数据、状态、校验报告和审计摘要。验证重试执行完整静态校验；预览接口只为静态安全的当前版本创建受控 URL。load-check 的 POST 只触发可信检查任务，不接受状态字段；GET 只供管理端轮询。检查器通过内部接口写结果，管理员 API 不提供结果写入能力。发布和撤回遵守状态机；删除仅接受符合条件的草稿并要求二次确认值。

管理列表可按状态、市场、公司或代码筛选，并使用游标分页。所有响应隐藏服务器绝对路径和内部异常。

## 发布与撤回事务

发布流程：

```text
BEGIN
→ SELECT snapshot_index ... FOR UPDATE
→ 重算 content_sha256
→ 校验状态、version、nonce、静态校验 clean 和可信 load-check passed
→ 原子移动 HTML 到 published 路径
→ 更新索引状态、路径、published_at 和 version
→ 追加审计记录
→ COMMIT
```

发布 API 必须在行锁内重新计算 `content_sha256`，并要求当前 `version`、`nonce` 对应的可信 load-check 为 `passed`，同时验证静态校验为 `clean`；任一状态缺失、失败、过期或绑定旧文件时返回 409。撤回以相同方式锁定记录，把 HTML 原子移出公开路径，更新状态、路径和版本，并追加审计记录。索引状态、文件系统状态和审计结果必须作为一个业务事务完成。

数据库无法回滚文件系统，因此 service 在移动前登记补偿动作；数据库失败时恢复原文件位置。进程意外退出后，启动校验任务只报告索引与目录差异，不静默修改已发布内容。事务完成前，公开索引不能暴露新状态。

## 审计日志

审计日志只追加，不提供修改或删除 API。至少记录登录成功/失败、HTML 导入或替换、验证重试、发布、撤回、草稿删除和密码修改。每条记录包含 `actor_id`、`snapshot_id`、动作、`request_id`、幂等键摘要、旧/新状态、文件哈希或路径变化摘要和 ISO 8601 时间。

审计详情不得保存 HTML 正文、Session 原文、CSRF 原文、密码、完整 Cookie 或服务器密钥。目标记录被删除后保留审计行；审计日志至少保留 365 天。

## 错误、幂等与并发

错误响应统一为：

```json
{
  "error": {
    "code": "snapshot_validation_failed",
    "message": "HTML 校验失败",
    "details": [],
    "request_id": "req_01..."
  }
}
```

常用状态码为 400 请求或文件格式错误、401 会话失效、403 CSRF 或权限失败、404 公开资源不可见、409 重复版本/状态冲突/文件变化、413 文件超限、422 字段校验失败、429 限流和 500 未预期错误。500 响应不返回堆栈。

导入、扫描、发布、撤回和删除接受 `Idempotency-Key`。相同管理员、接口和请求体使用同一键重试时返回原结果；键与不同请求体冲突时返回 409。所有变更请求携带期望 `version` 或 `If-Match`，不匹配时返回 409。发布与撤回同时使用数据库行锁，避免两个请求交错写文件和状态。每次写操作记录 `request_id`，便于追查超时后的结果。

## OpenAPI 与测试

FastAPI 生成 OpenAPI；开发环境提供受控文档，生产环境关闭交互页或限制管理员访问。CI 根据 OpenAPI 生成 Nuxt 与管理端 TypeScript 客户端。不兼容契约变化必须先升级 API 版本，并同步生成客户端与本文。

单元测试覆盖元数据、结构、安全、远程资源、MIME、大小、路径和 SHA-256 静态校验。集成测试覆盖登录 Content-Type、Origin/Referer、Session/CSRF、Strict Cookie、受控预览 URL 绑定、可信检查器内部认证、nonce 失效、管理员不可写结果、PostgreSQL 迁移、游标、幂等键、乐观版本、文件补偿事务、审计只追加、发布和撤回可见性。检查器测试覆盖真实 `HEAD`、headless Chromium 的 sandboxed iframe、`load`/`error`/`timeout` 和权威结果写入；浏览器测试覆盖管理员本地预览、轮询、404、重试、`html-checking` 和错误阻断。
