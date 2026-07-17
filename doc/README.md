# 企业快照库文档

## 当前状态

项目当前完成的是可执行 HTML 原型：公开端以公司目录加阅读工作区展示快照，管理端演示 HTML 导入、校验、审核、发布与撤回。Nuxt、Vue 管理端、FastAPI、PostgreSQL 和 Docker 仍是下一阶段的生产目标，不应写成已经实现。

## 唯一内容主线

HTML 是网站唯一发布物。Skill 同时生成的 MD 只用于审计、复查和重新生成，不参与网站上传、解析、预览或发布。

## 从哪里开始

1. 打开 [prototype.html](./prototype.html) 查看当前交互。
2. 阅读 [DEVELOPMENT.md](./DEVELOPMENT.md) 了解产品范围、技术边界和实施顺序。
3. 按任务阅读 [PRODUCT_UI.md](./PRODUCT_UI.md)、[BACKEND.md](./BACKEND.md)、[DEPLOYMENT.md](./DEPLOYMENT.md) 或 [SEO.md](./SEO.md)。

## 样本资产

- `snapshots/published/`：原型直接读取的完整 HTML。
- `snapshots/sources/`：与 HTML 对应的审计源 MD；网站运行时不读取。

## 文档优先级

`doc/` 是当前开发依据。`docs/superpowers/specs/` 和 `docs/superpowers/plans/` 记录历史决策与实施过程；出现差异时，以本目录当前文档和已通过的测试为准。

## 下一步

按 [DEVELOPMENT.md](./DEVELOPMENT.md) 的实施顺序，从仓库骨架、HTML 内容契约和 FastAPI 索引开始建设生产代码。
