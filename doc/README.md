# 企业快照库文档

## 当前状态

Nuxt 公开端、Vue/Vite 管理端、FastAPI 健康接口、PostgreSQL、Nginx 和 Docker Compose 的工程骨架已经存在。资料上传、索引和阅读仍是下一段实现工作；`doc/prototype.html` 只说明交互方向，不代表运行中的业务服务。

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

下一里程碑实现按扩展名接收 HTML 与 Markdown、文件落盘、Markdown 渲染、公司和资料索引，以及公开阅读接口。资料直传完成前，不把本地未认证写入暴露到生产网络。
