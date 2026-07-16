# 企业快照库 API 设计

## 设计原则

- 使用 REST 风格和 `/api/v1` 版本前缀。
- 公开、认证和管理员接口分组。
- JSON 字段使用 `snake_case`，时间使用含时区 ISO 8601。
- 列表使用游标分页。
- 所有写操作进入 service 和文件事务层。
- 错误响应统一，服务端日志保留内部追踪信息。

## 基础响应

单项成功响应直接返回资源对象。列表返回：

```json
{
  "items": [],
  "next_cursor": null,
  "previous_cursor": null,
  "total": 0
}
```

错误响应：

```json
{
  "error": {
    "code": "snapshot_validation_failed",
    "message": "Markdown 校验失败",
    "details": [
      {
        "field": "frontmatter.market",
        "level": "error",
        "message": "market 必须是 CN 或 HK"
      }
    ],
    "request_id": "req_01..."
  }
}
```

## 认证

管理端使用服务端 Session：

- Session ID 存入 HttpOnly、Secure、SameSite=Lax Cookie。
- Session 原文不存数据库，只保存哈希。
- 默认闲置 12 小时失效，最长 7 天。
- 登录成功后轮换 Session。
- 所有非 GET 管理请求必须提交 CSRF Token。

首版不提供公开 API Token。

## 公开接口

### 快照列表

```http
GET /api/v1/public/snapshots
```

查询参数：

| 参数 | 说明 |
|---|---|
| `q` | 公司名称或证券代码，最长 80 字符 |
| `market` | `CN` 或 `HK` |
| `sort` | `data_desc`、`published_desc`、`name_asc` |
| `cursor` | 分页游标 |
| `limit` | 默认 24，最大 60 |
| `latest_only` | 默认 `true` |

响应项：

```json
{
  "id": "01J...",
  "company_name": "腾讯控股",
  "ticker": "00700",
  "market": "HK",
  "exchange": "HKEX",
  "data_as_of": "2025-12-31",
  "published_at": "2026-07-16T10:30:00+08:00",
  "summary": "现金流和资产负债表稳健，仍需验证增长持续性。",
  "verdict": "second_round",
  "metrics": {
    "pe_ttm": 18.2,
    "pb": 3.4,
    "dividend_yield_pct": 2.1
  },
  "path": "/snapshots/HK/00700/2025-12-31"
}
```

### 最新快照

```http
GET /api/v1/public/snapshots/{market}/{ticker}
```

返回该公司最新已发布版本。

### 指定版本

```http
GET /api/v1/public/snapshots/{market}/{ticker}/{data_as_of}
```

详情响应包括元数据、安全 HTML、目录和已发布历史版本。API 不返回服务器文件路径和原始 Markdown。

```json
{
  "snapshot": {},
  "html": "<h2 id=\"...\">...</h2>",
  "toc": [
    {"level": 2, "text": "一、入口检验", "anchor": "一入口检验"}
  ],
  "versions": [
    {"data_as_of": "2025-12-31", "path": "/snapshots/HK/00700/2025-12-31"}
  ]
}
```

## 认证接口

### 登录

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "..."
}
```

成功后设置 Session Cookie，并返回管理员基本信息和 CSRF Token。

### 当前管理员

```http
GET /api/v1/auth/me
```

### 退出

```http
POST /api/v1/auth/logout
X-CSRF-Token: ...
```

### 修改密码

```http
POST /api/v1/auth/change-password
X-CSRF-Token: ...
```

修改成功后撤销其他 Session，并轮换当前 Session。

## 管理员接口

### 快照列表

```http
GET /api/v1/admin/snapshots?status=draft&market=HK&q=腾讯
```

管理员列表可查看 `draft`、`published` 和 `withdrawn`，并返回错误、警告数量。

### 上传 Markdown

```http
POST /api/v1/admin/snapshots/import
Content-Type: multipart/form-data
X-CSRF-Token: ...
```

表单字段：

- `file`：单个 `.md`。
- `replace_draft`：默认 `false`。

导入成功返回草稿资源和完整校验报告。存在错误时不写入草稿目录。

### 扫描 inbox

```http
POST /api/v1/admin/snapshots/scan-inbox
X-CSRF-Token: ...
```

扫描只处理 `content/inbox/` 顶层和规定子目录中的普通文件。单次最多处理 100 个文件，结果逐项返回。

### 草稿详情和预览

```http
GET /api/v1/admin/snapshots/{id}
GET /api/v1/admin/snapshots/{id}/preview
```

预览返回与公开页相同的安全 HTML，不把原始 Markdown 暴露给浏览器日志。

### 发布

```http
POST /api/v1/admin/snapshots/{id}/publish
X-CSRF-Token: ...
```

发布前重新校验文件哈希和内容。如果文件自导入后被外部修改，返回 `409 snapshot_changed`。

### 撤回

```http
POST /api/v1/admin/snapshots/{id}/unpublish
X-CSRF-Token: ...
```

撤回后公开接口立即返回 `404`，文件移回草稿目录，frontmatter 状态改回 `draft`，数据库状态记为 `withdrawn`，审计记录保留。

### 删除草稿

```http
DELETE /api/v1/admin/snapshots/{id}
X-CSRF-Token: ...
```

只允许删除未发布草稿。请求体提交证券代码用于二次确认。

## 健康检查

```http
GET /api/health/live
GET /api/health/ready
```

- `live` 只检查进程存活。
- `ready` 检查数据库连接和内容目录可读写。
- Nginx 和 Docker 使用 `ready` 判断是否接收流量。

## 状态码

| 状态码 | 场景 |
|---|---|
| `200` | 查询或操作成功 |
| `201` | 导入成功 |
| `204` | 退出或删除成功 |
| `400` | 文件或请求格式错误 |
| `401` | 未登录或 Session 失效 |
| `403` | CSRF 失败或权限不足 |
| `404` | 公开资源不存在 |
| `409` | 版本重复、状态冲突、文件被修改 |
| `413` | 文件超过 2 MiB |
| `422` | 字段校验失败 |
| `429` | 登录或接口访问过快 |
| `500` | 未预期服务端错误 |

## 幂等和并发

- 同一文件内容使用 SHA-256 识别重复导入。
- 发布操作对同一快照加数据库行锁。
- 文件移动、索引状态和审计记录组成一个补偿事务。
- 文件移动成功而数据库失败时，服务自动回滚文件位置。
- 所有写操作记录 `request_id`，便于追查重试结果。

## 限流

| 接口 | 限制 |
|---|---|
| 登录 | 每 IP 每 15 分钟 10 次 |
| 公开列表和详情 | 每 IP 每分钟 120 次 |
| 上传和扫描 | 每管理员每分钟 20 次 |

首版可在 FastAPI 进程内实现登录限流；如果以后横向扩展，再引入共享限流存储。

## OpenAPI

- FastAPI 在开发环境提供 `/api/docs`。
- 生产环境关闭交互文档或限制管理员访问。
- CI 根据 OpenAPI 生成管理端和 Nuxt 的 TypeScript 客户端。
- OpenAPI 发生不兼容变化时，必须同时更新本文和前端客户端。
