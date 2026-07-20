# 企业快照库文档

## 当前状态

直接资料上传垂直切片已经完成。当前仓库包含 Nuxt 公开资料工作区、Vue/Vite 管理端、FastAPI 公司与资料接口、PostgreSQL 索引、持久化内容目录、Nginx 和 Docker Compose；管理员可以创建公司并上传 HTML/Markdown，公开端可以按公司阅读已经入库的资料。`doc/prototype.html` 仍只作为交互参考。

本次直传切片允许未认证写入，范围只限本地开发与验收。它不构成生产部署方案；生产写入仍需要在后续工作中接入管理员认证、授权和 CSRF 防护。

## 资料主线

HTML 和 Markdown 都可以上传。管理员为公司选择一个或多个文件后，系统保存源文件、为 Markdown 生成展示页并建立资料索引；写入索引后，公开阅读区可以立即打开资料。

HTML 原文件与 Markdown 生成页使用同一个 iframe 阅读器。Markdown 模板、示例和预览位于 [templates/markdown/](./templates/markdown/README.md)，可直接打开 [templates/markdown/showcase.html](./templates/markdown/showcase.html) 查看三类资料的版式。

## 从哪里开始

1. 阅读仓库根目录 [README.md](../README.md) 运行工程骨架。
2. 阅读 [DEVELOPMENT.md](./DEVELOPMENT.md) 了解资料主线、范围和实施顺序。
3. 按任务阅读 [PRODUCT_UI.md](./PRODUCT_UI.md)、[BACKEND.md](./BACKEND.md)、[DEPLOYMENT.md](./DEPLOYMENT.md) 或 [SEO.md](./SEO.md)。
4. 阅读已确认的 [资料直接上传与 Markdown 渲染设计](./specs/2026-07-18-direct-document-upload-design.md)。

## 文档优先级

`doc/` 是当前开发依据。`docs/superpowers/specs/` 和 `docs/superpowers/plans/` 记录历史决策与实施过程；出现差异时，以本目录当前文档和已通过的测试为准。

## 下一步

下一里程碑是管理员认证和生产写入边界：建立登录与会话、按管理员身份授权写操作、加入 CSRF 防护，并明确生产环境的网络暴露、密钥、备份和恢复规则。完成这些工作前，继续把未认证管理端和写接口限制在本地开发与验收环境。
