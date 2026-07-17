# 企业快照库开发总纲

## 项目目标

保存并阅读 A 股、港股及无上市代码公司的企业研究快照。首版先跑通多公司 HTML 快照的导入、审核、发布和公开阅读。

## 当前实现与目标实现

- 已实现：`doc/prototype.html` 和两家公司样本，覆盖公开工作区、移动抽屉、管理审核、发布状态与加载失败。
- 目标实现：Nuxt 公开端、Vue/Vite 管理端、FastAPI、PostgreSQL、Nginx 和 Docker Compose。

## 唯一内容主线

Codex Skill 生成 HTML 与 MD。HTML 经过校验、人工审核后发布，是网站唯一发布物；MD 只用于审计和重新生成，不参与网站运行。

## 首版范围

包含多公司目录、HTML 阅读、搜索筛选、管理员认证、HTML 上传或扫描、安全校验、审核、发布、撤回、审计、SEO 基础和阿里云部署。不包含在线编辑器、网站内运行 Skill、行情实时刷新、社区功能或复杂组合管理。

## 技术栈

公开端使用 Nuxt、Vue 和 TypeScript；管理端使用 Vue、Vite 和 TypeScript；API 使用 FastAPI；索引和审计使用 PostgreSQL；入口使用 Nginx；本地和阿里云使用 Docker Compose。

## 系统边界

Skill 在网站外运行。只有 FastAPI 可以写生产内容目录和发布状态。Nuxt 与管理端通过 API 读取元数据；公开端与管理端预览同一个 HTML 文件并采用相同 sandbox 规则。数据库不保存 HTML 正文。

## 数据流

Skill → HTML 安全与元数据校验 → 草稿 → 人工审核 → 发布 → 公开阅读。任一文件缺失或加载失败都会形成审核错误并阻断发布。

## 文档地图

- [PRODUCT_UI.md](./PRODUCT_UI.md)：公开端和管理端交互。
- [BACKEND.md](./BACKEND.md)：API、索引、状态、校验和审计。
- [DEPLOYMENT.md](./DEPLOYMENT.md)：Docker、Nginx、阿里云、备份和回滚。
- [SEO.md](./SEO.md)：独立 HTML 地址的索引策略。

## 开发约定

OpenAPI 是前后端契约来源；内容状态变化必须事务化并记录审计；HTML 只能通过统一校验器进入发布状态；文档必须区分“当前已实现”和“目标设计”。

## 测试层级

使用单元测试覆盖元数据和安全校验，集成测试覆盖文件事务与发布状态，浏览器测试覆盖公开目录、管理操作、404、重试、iframe 清理与移动抽屉。

## 实施顺序

1. 建立 Nuxt、Vue/Vite、FastAPI 和 Compose 仓库骨架。
2. 实现 HTML 元数据、安全校验和内容路径契约。
3. 建立 PostgreSQL 迁移、管理员认证和审计。
4. 实现导入、审核、发布、撤回和公开读取 API。
5. 将已验证的原型交互迁移到公开端和管理端。
6. 完成 Nginx、阿里云、SEO、备份和发布检查。
