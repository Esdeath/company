# 企业快照库文档

## 当前状态

工程骨架已完成：Nuxt 公开端、Vue/Vite 管理端、FastAPI 健康接口、PostgreSQL、Nginx 和 Docker Compose 已进入生产代码。根目录质量检查、五服务健康检查、非 root 运行、路由、端口边界和 PostgreSQL 失效恢复均已通过验收。

业务功能仍停留在可执行 HTML 原型。`doc/prototype.html` 和两家公司样本覆盖公开工作区、移动抽屉、管理审核、发布状态与加载失败；生产代码尚未实现 HTML 导入、校验、发布、认证或公开快照读取。

## 唯一内容主线

HTML 是网站唯一发布物。Skill 同时生成的 MD 只用于审计、复查和重新生成，不参与网站上传、解析、预览或发布。

## 从哪里开始

1. 阅读仓库根目录 [README.md](../README.md) 运行工程骨架。
2. 打开 [prototype.html](./prototype.html) 查看目标交互。
3. 阅读 [DEVELOPMENT.md](./DEVELOPMENT.md) 了解产品范围、技术边界和实施顺序。
4. 按任务阅读 [PRODUCT_UI.md](./PRODUCT_UI.md)、[BACKEND.md](./BACKEND.md)、[DEPLOYMENT.md](./DEPLOYMENT.md) 或 [SEO.md](./SEO.md)。

## 样本资产

- `snapshots/published/`：原型直接读取的完整 HTML。
- `snapshots/sources/`：与 HTML 对应的审计源 MD；网站运行时不读取。

## 文档优先级

`doc/` 是当前开发依据。`docs/superpowers/specs/` 和 `docs/superpowers/plans/` 记录历史决策与实施过程；出现差异时，以本目录当前文档和已通过的测试为准。

## 下一步

下一里程碑是“HTML 内容契约与后端静态校验核心”。先实现元数据提取、内容路径、SHA-256 与静态安全校验，再进入 PostgreSQL 业务表、认证和发布流程。
