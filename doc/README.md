# 企业快照库文档

## 当前状态

直接资料上传垂直切片已经完成。当前仓库包含 Nuxt 公开资料工作区、Vue/Vite 管理端、FastAPI 公司与资料接口、PostgreSQL 索引、持久化内容目录、Nginx 和 Docker Compose；管理员可以创建公司并上传 HTML/Markdown，公开端可以按公司阅读已经入库的资料。`doc/prototype.html` 仍只作为交互参考。

管理员认证里程碑已经实现：单管理员使用 Argon2 密码哈希，登录后获得数据库会话和 `HttpOnly` Cookie，所有写操作都要求会话绑定的 CSRF 令牌。宿主机 Nginx 可通过 HTTPS 公开 `/admin/`，容器端口仍只绑定回环地址，不再需要 SSH 隧道。

## 资料主线

HTML 和 Markdown 都可以上传。管理员为公司选择一个或多个文件后，系统保存源文件、为 Markdown 生成展示页并建立资料索引；写入索引后，公开阅读区可以立即打开资料。

HTML 原文件与 Markdown 生成页使用同一个 iframe 阅读器。Markdown 模板、示例和预览位于 [templates/markdown/](./templates/markdown/README.md)，可直接打开 [templates/markdown/showcase.html](./templates/markdown/showcase.html) 查看三类资料的版式。

## 从哪里开始

1. 阅读仓库根目录 [README.md](../README.md) 运行工程骨架。
2. 阅读 [DEVELOPMENT.md](./DEVELOPMENT.md) 了解资料主线、范围和实施顺序。
3. 按任务阅读 [PRODUCT_UI.md](./PRODUCT_UI.md)、[BACKEND.md](./BACKEND.md)、[DEPLOYMENT.md](./DEPLOYMENT.md) 或 [SEO.md](./SEO.md)。
4. 阅读 [管理员认证、会话与 CSRF](./AUTHENTICATION.md) 了解公网管理入口的安全契约。
5. 阅读已确认的 [资料直接上传与 Markdown 渲染设计](./specs/2026-07-18-direct-document-upload-design.md)。

## 部署复盘

[从本地 Docker Compose 到阿里云 ECS：企业研究资料库部署实录](./ALIYUN_ECS_DEPLOYMENT_RETROSPECTIVE.md) 记录了本轮实际部署中的错误、诊断命令、离线 AMD64 镜像方案、HTTPS、SSH 隧道和备份过程，可作为公开技术文章或故障复盘使用。

## 文档优先级

`doc/` 是当前开发依据。`docs/superpowers/specs/` 和 `docs/superpowers/plans/` 记录历史决策与实施过程；出现差异时，以本目录当前文档和已通过的测试为准。

## 下一步

管理员公网写入边界已经完成，日常更新可直接运行 `make deploy-aliyun`。下一步可在实际使用一段时间后选择加入登录失败审计与告警、二次验证或多管理员角色；当前部署、更新、回滚和本地备份规则以 [DEPLOYMENT.md](./DEPLOYMENT.md) 为准。
