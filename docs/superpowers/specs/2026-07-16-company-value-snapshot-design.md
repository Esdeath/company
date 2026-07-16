# A 股与港股企业快照网站设计

日期：2026-07-16

## 1. 目标

建立一个移动优先的公司财务快照网站，跑通以下最小闭环：

1. 用户在 Codex 中输入 A 股或港股公司名称、代码。
2. 本地 `hk-value-snapshot` Skill 获取公开财报和行情数据，生成企业快照 Markdown。
3. 管理员将 Markdown 上传管理端，或把文件放进 `content/inbox/`。
4. FastAPI 校验文件，管理端预览并确认发布。
5. Nuxt 前台展示已发布的公司快照。

网站不在服务器内运行 Codex、AI Agent 或 Skill。Skill 与网站以 Markdown 文件为唯一交付契约。

## 2. 首版范围

### 2.1 支持

- A 股：上海证券交易所、深圳证券交易所。
- 港股：香港交易所。
- 单管理员登录。
- Markdown 上传和 `content/inbox/` 目录扫描。
- Markdown 元数据及正文结构校验。
- 草稿预览、发布、撤回、删除草稿。
- 公开公司快照列表。
- 按公司名称、证券代码和市场搜索或筛选。
- 快照 Markdown 安全渲染。
- Docker Compose 一键启动全部网站服务。

### 2.2 不支持

- 网站后台调用 AI 或 Skill。
- 网站自动抓取财报、行情或公司资料。
- 美股和其他市场。
- 产品、用户、行业、管理层和企业文化专题。
- 用户注册、投稿和多人协作。
- 图片、视频、PDF 和文档托管。
- 长期盈利预测、目标价和买卖建议。
- Skill 生成的 HTML 文件导入和展示。

## 3. 核心设计原则

1. **Markdown 是内容事实来源。** PostgreSQL 不保存 Markdown 正文。
2. **Skill 和网站解耦。** Skill 只需遵守 Markdown 契约，网站不依赖其内部取数实现。
3. **市场差异留在 Skill 内。** A 股与港股使用不同数据适配器，但输出相同结构。
4. **只发布实际数据和直接运算。** 保留现有 Skill 的“不预测、不估算、不评级”边界。
5. **发布必须人工确认。** 导入成功不等于公开发布。
6. **移动优先。** 手机端完成查找和阅读，管理端在手机可用、桌面效率更高。

## 4. 系统架构

项目使用单仓库管理三个独立应用：

```text
apps/
├── web/                  # Nuxt + TypeScript，公开前台
├── admin/                # Vue 3 + Vite + TypeScript，管理端
└── api/                  # FastAPI + Python，后台 API
content/
├── inbox/                # Skill 或人工放入的待导入 Markdown
├── drafts/               # 校验通过但未发布的 Markdown
└── published/
    ├── CN/               # A 股已发布快照
    └── HK/               # 港股已发布快照
skills/
└── hk-value-snapshot/    # 现有快照 Skill，需统一 A/H 输出契约
infra/
└── caddy/                # 反向代理配置
docs/
compose.yaml
.env.example
```

运行服务：

- `web`：Nuxt 服务端渲染公开页面。
- `admin`：Vue/Vite 构建的管理端 SPA。
- `api`：登录、导入、校验、索引、发布和公开 API。
- `postgres`：管理员、快照索引和操作日志。
- `proxy`：统一域名、HTTPS 和路径路由。

不引入 Redis、任务 Worker、MinIO 或消息队列。

## 5. Markdown 内容契约

### 5.1 文件路径

草稿文件：

```text
content/drafts/{market}/{ticker}/{data_as_of}.md
```

发布文件：

```text
content/published/{market}/{ticker}/{data_as_of}.md
```

示例：

```text
content/published/CN/600519/2026-07-16.md
content/published/HK/00700/2026-07-16.md
```

同一公司同一数据日期只允许存在一份已发布快照。重新导入时必须选择覆盖草稿或保留原文件，不能静默覆盖已发布文件。

### 5.2 必填 frontmatter

```yaml
---
schema_version: 1
type: value_snapshot
title: 价值线企业快照版 — 腾讯控股
company_name: 腾讯控股
ticker: "00700"
market: HK
exchange: HKEX
reporting_currency: CNY
quote_currency: HKD
data_as_of: 2026-07-16
generated_at: 2026-07-16T10:30:00+08:00
generator: hk-value-snapshot
status: draft
verdict: second_round
summary: 入口未到历史低位，现金流质量稳定，需继续核查资本配置。
source_urls:
  - https://example.com/financial-source
  - https://example.com/quote-source
---
```

字段约束：

- `schema_version` 首版固定为 `1`。
- `type` 固定为 `value_snapshot`。
- `ticker` 必须是字符串，保留前导零。
- `market` 只能是 `CN` 或 `HK`。
- `exchange` 只能是 `SSE`、`SZSE` 或 `HKEX`。
- `CN` 对应 `SSE` 或 `SZSE`；`HK` 对应 `HKEX`。
- `data_as_of` 是行情和快照对应的数据日期，不是上传日期。
- `status` 只能是 `draft` 或 `published`。
- `verdict` 只能是 `second_round` 或 `skip`，分别对应“进入第二轮”和“翻页”。
- `summary` 是首页使用的一句话结论，最多 120 个中文字符。
- `source_urls` 至少包含一个有效的 HTTP 或 HTTPS 地址。
- 发布时 API 将 `status` 改为 `published`，并原子移动到 `content/published/`。
- 发布时 API 增加 `published_at`；撤回时移除该字段。

### 5.3 正文结构

Skill 继续使用固定模块顺序：

1. 标题与数据日期。
2. 价格、PE、PB、股息率和市值。
3. 30 秒结论。
4. 公司业务与商业模式。
5. 企业快照上半部。
6. 企业快照下半部。
7. 5 秒心算。
8. 资本结构与流动性。
9. 年均变化率。
10. 五问检查清单。
11. 数据来源、口径注释和免责声明。

网站不从正文重新推断证券代码、市场或数据日期；这些信息必须来自 frontmatter。

### 5.4 A 股与港股适配

现有 Skill 的说明、模板和校验主要按港股编写，但数据接口参考已经列出 A 股接口。正式接入前必须统一：

- Skill 描述同时触发 A 股和港股请求。
- 根据代码或明确市场选择 `CN` 或 `HK` 数据适配器。
- A 股区分 `SSE` 与 `SZSE`。
- 港股继续处理财报币种与港元行情的折算。
- A 股使用人民币报价，不套用港股汇率、股息和历史股本规则。
- 模板中的 `.HK`、`HK$`、港元市值等固定文字改为变量。
- 两个适配器最终生成完全相同的 frontmatter 和正文模块。
- Skill 增加可选输出目录参数；在本项目中指定为 `content/inbox/`，未指定时仍输出到项目根目录。

Skill 可以暂时保留 `hk-value-snapshot` 名称，但其 description 必须明确包含 A 股触发条件，避免 A 股请求无法触发。

## 6. 用户流程

### 6.1 生成

1. 用户在 Codex 中请求为一家公司生成企业快照。
2. Skill 识别市场和证券代码；无法唯一识别时要求用户确认。
3. Skill 获取并核验数据，生成 Markdown 和 HTML。
4. 网站只使用 Markdown；HTML 留作独立交付文件。

### 6.2 导入

支持两种方式：

- 在管理端选择一个 `.md` 文件上传。
- 把 `.md` 文件放入 `content/inbox/`，然后在管理端点击“扫描待导入文件”。

API 按以下顺序处理：

1. 检查扩展名、UTF-8 编码和文件大小。
2. 解析 YAML frontmatter。
3. 校验字段、市场和正文必需章节。
4. 检查目标公司、日期是否重复。
5. 将通过校验的文件原子写入 `content/drafts/`。
6. 更新 PostgreSQL 快照索引。
7. 返回预览地址和警告信息。

任何一步失败都不得产生半写入文件。

### 6.3 发布

1. 管理员打开草稿预览。
2. 页面同时显示公司、代码、市场、数据日期和来源链接。
3. 管理员确认发布。
4. API 更新 frontmatter 状态并原子移动文件。
5. API 更新索引并写入操作日志。
6. 公开 API 立即可读取新快照。

撤回发布会把文件移回草稿目录并保留内容。首版不提供已发布文件的物理删除；只能撤回后再删除草稿。

## 7. 页面设计

### 7.1 公开首页

- 网站名称和一句简短说明。
- 公司名称或证券代码搜索。
- 市场筛选：全部、A 股、港股。
- 公司卡片显示公司名称、代码、市场、数据日期和结论印章。
- 默认按数据日期倒序。
- 手机单列，宽屏使用两至三列。

### 7.2 快照详情

- 顶部显示公司名称、代码、市场和数据日期。
- 明确提示“实际披露数据与直接运算，不构成投资建议”。
- 渲染完整 Markdown 正文和 GFM 表格。
- 提供来源链接。
- 有多期快照时，可从简单日期下拉框切换；不做图表对比。

### 7.3 后台登录

- 用户名和密码。
- 不提供注册、找回密码和第三方登录。
- 登录失败使用统一错误信息，避免泄漏账号是否存在。

### 7.4 快照管理

- 草稿、已发布两个标签页。
- 上传 Markdown。
- 扫描 `content/inbox/`。
- 显示校验错误和警告。
- Markdown 预览。
- 发布、撤回和删除草稿。
- 按名称、代码和市场筛选。

## 8. API 边界

### 8.1 认证

```text
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
```

### 8.2 管理端

```text
GET    /api/admin/snapshots
POST   /api/admin/snapshots/import
POST   /api/admin/snapshots/scan-inbox
GET    /api/admin/snapshots/{id}
GET    /api/admin/snapshots/{id}/preview
POST   /api/admin/snapshots/{id}/publish
POST   /api/admin/snapshots/{id}/unpublish
DELETE /api/admin/snapshots/{id}
```

### 8.3 公开端

```text
GET /api/public/snapshots
GET /api/public/snapshots/{market}/{ticker}
GET /api/public/snapshots/{market}/{ticker}/{data_as_of}
```

公开列表只返回元数据和摘要，不返回全部 Markdown。详情接口返回经过解析的元数据与原始 Markdown 正文。

## 9. 数据库

首版仅包含三类表：

- `admin_users`：管理员用户名、密码哈希、创建时间和状态。
- `snapshot_index`：文件路径、公司、代码、市场、数据日期、状态、标题、摘要和更新时间。
- `audit_logs`：导入、发布、撤回和删除草稿记录。

`snapshot_index` 是派生索引，必须能通过扫描 `content/drafts/` 和 `content/published/` 完整重建。

首个管理员不通过公开接口创建。API 第一次启动时读取环境变量 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD`：数据库尚无管理员时创建账号，已经存在时忽略这两个值。部署完成后应从环境配置中移除明文初始密码，并通过受保护的管理接口修改密码。

## 10. 安全与错误处理

- 密码使用 Argon2id 哈希。
- 登录使用 HttpOnly、Secure、SameSite Cookie。
- 所有修改请求验证 CSRF Token。
- 上传只接受 UTF-8 `.md`，首版最大 2 MB。
- 拒绝路径穿越、符号链接和包含空字节的文件名。
- Markdown 禁止原始 HTML，使用标签白名单渲染，阻止 XSS。
- 外部链接添加 `rel="noopener noreferrer"`。
- YAML 解析使用安全模式，不实例化任意对象。
- 写文件采用同目录临时文件加原子重命名。
- 无效文件保留在 `content/inbox/`，后台显示错误，不自动删除。
- 数据库与内容索引不一致时，以磁盘 Markdown 为准并重建索引。

## 11. Docker 部署

`compose.yaml` 包含：

- `proxy`
- `web`
- `admin`
- `api`
- `postgres`

持久化：

- PostgreSQL 使用命名卷。
- `content/` 使用宿主机绑定挂载，便于 Codex Skill 直接写入和 Git 管理。
- 代码打包进镜像，不在运行时修改。

网站不自动执行 Git commit 或 push。管理员完成发布后，可在宿主机检查 `content/` 变化并人工提交；远程仓库凭证不进入应用容器。

健康检查：

- API 提供 `/api/health/live` 和 `/api/health/ready`。
- PostgreSQL 使用 `pg_isready`。
- Proxy 只在上游服务健康后转发请求。

路由：

- `/api/*` → FastAPI
- `/admin/*` → Vue Admin
- 其他路径 → Nuxt Web

## 12. 测试与验收

### 12.1 单元测试

- A 股和港股 frontmatter 校验。
- 证券代码前导零保留。
- 市场与交易所组合校验。
- 必需章节检查。
- Markdown HTML/XSS 清理。
- 文件目标路径计算。
- 重复快照处理。

### 12.2 API 集成测试

- 登录成功、失败和退出。
- 未认证用户不能访问管理接口。
- 上传有效 A 股和港股 Markdown。
- 上传无效 YAML、错误市场、超大文件和危险文件名。
- 导入、预览、发布、撤回和删除草稿完整流程。
- 索引清空后可以从 Markdown 重建。

### 12.3 前端测试

- 首页搜索和市场筛选。
- Markdown 表格在手机端可横向滚动。
- 详情页正确显示元数据、来源和免责声明。
- 后台显示校验错误并阻止发布。

### 12.4 端到端验收

使用一份 A 股和一份港股样例完成：

1. Docker Compose 启动成功。
2. 管理员登录。
3. 导入两个 Markdown。
4. 预览内容和表格。
5. 发布。
6. 前台按市场和代码找到两家公司。
7. 打开详情并验证数据日期、来源和正文。
8. 撤回其中一份，前台立即不可见。

## 13. 实施顺序

1. 统一 Skill 的 A 股/港股 Markdown 契约，并生成两份固定测试样例。
2. 建立 Monorepo、Docker Compose 和服务健康检查。
3. 实现 FastAPI 文件导入、校验、索引和认证。
4. 实现管理端导入、预览与发布。
5. 实现 Nuxt 首页和快照详情。
6. 完成端到端测试和 Docker 部署验证。

这一顺序先固定输入契约，再实现消费者，避免网站围绕不稳定模板返工。
