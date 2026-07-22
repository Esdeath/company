# 企业快照库开发总纲

## 项目目标

保存并阅读 A 股、港股及无上市代码公司的企业研究资料。首版接收不同 Skill 或人工整理的 HTML 和 Markdown，不要求统一业务字段。

## 当前实现与目标实现

- 工程骨架已具备 Nuxt、Vue/Vite、FastAPI 健康接口、PostgreSQL、Nginx 和 Docker Compose。
- `doc/prototype.html` 是交互参考，不代表资料服务已实现。
- 本轮目标是直接资料上传：选择公司、保存文件、写入索引和公开阅读。

## 资料主线

Skill 或人工资料 → 管理员选择公司 → 上传 HTML/Markdown → 按文件保存并建立索引 → 立即公开阅读

管理员可以选择既有公司或新建公司，再选择一个或多个 `.html`、`.md` 文件。HTML 保留原文件；Markdown 保留源文件并生成展示 HTML。资料成功写入索引后，公开目录和阅读器即可读取它。

管理员选择或新建公司后上传 HTML 和 Markdown；资料写入索引后立即公开。

## 首版范围

包含公司目录、资料列表、HTML 与 Markdown 多文件上传、按文件结果、统一 iframe 阅读器、Markdown 模板、移动端公司抽屉、基础 SEO、Docker Compose 和阿里云部署边界。不包含在线编辑器、网站内运行 Skill、行情实时刷新、社区功能或正文搜索。

## 技术栈

公开端使用 Nuxt、Vue 和 TypeScript；管理端使用 Vue、Vite 和 TypeScript；API 使用 FastAPI；公司与资料索引使用 PostgreSQL；入口使用 Nginx；本地和阿里云使用 Docker Compose。

## 系统边界

Skill 在网站外运行。HTML 和 Markdown Skill 输出视为可信管理员输入；系统按扩展名处理文件，不检查正文、远程资源、脚本、业务元数据或重复内容。公开端与管理端使用同一个空 `sandbox` iframe 阅读器。数据库保存公司与资料索引，不保存文件正文。

写入接口只接受已登录管理员，并同时校验服务器会话与 `X-CSRF-Token`。本地开发使用非 Secure Cookie，生产必须设置 `SESSION_COOKIE_SECURE=true` 并只通过 HTTPS 宿主机 Nginx 进入；容器端口仍不得直接暴露公网。

## 数据流

管理员选择或新建公司，上传 HTML 或 Markdown。FastAPI 写入源文件；Markdown 在写入时生成展示 HTML；服务完成索引写入后返回每个文件的结果。一个文件失败时服务清理该文件的临时数据，保留同批次中已经完成的文件。

## 文档地图

- [PRODUCT_UI.md](./PRODUCT_UI.md)：公司选择、上传和阅读交互。
- [BACKEND.md](./BACKEND.md)：文件、索引、接口和失败处理。
- [DEPLOYMENT.md](./DEPLOYMENT.md)：Docker、Nginx、阿里云、备份和网络边界。
- [SEO.md](./SEO.md)：已建立索引的资料内容的索引策略。
- [资料直接上传与 Markdown 渲染设计](./specs/2026-07-18-direct-document-upload-design.md)：已确认的直传设计。

## 开发约定

OpenAPI 是前后端接口契约来源。文件和索引写入要以单个文件为边界完成清理与补偿；文档应区分当前实现、目标设计和仅限本地的直传切片。

## 测试层级

单元测试覆盖标题提取、扩展名分流和 Markdown 渲染；集成测试覆盖临时文件清理、文件与索引写入及批量逐文件结果；浏览器测试覆盖公司选择、多文件上传、资料列表、iframe 阅读和移动抽屉。

## 实施顺序

1. 已完成：建立 Nuxt、Vue/Vite、FastAPI 和 Compose 仓库骨架。
2. 实现 HTML 与 Markdown 的按扩展名写入、标题提取和资料索引。
3. 实现 Markdown 模板渲染、单文件失败清理和批量结果。
4. 实现公开目录、资料列表和统一 iframe 阅读。
5. 将交互迁移到公开端和管理端，并完成移动端抽屉。
6. 加入管理员登录、服务器会话、CSRF 与公网 Nginx 速率限制，再开放 HTTPS 管理入口。
