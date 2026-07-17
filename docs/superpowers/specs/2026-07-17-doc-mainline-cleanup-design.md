# `doc/` 主线整理设计

## 目标

整理 `doc/`，让它成为项目当前开发依据，而不是同时保存互相冲突的 Markdown 解析架构和 HTML 发布架构。

整理完成后，读者从 `doc/README.md` 进入，能够快速确认：

- 产品当前做到什么程度；
- 网站实际接收和发布什么文件；
- 前台、管理端、后端和部署分别由哪份文档说明；
- 原型与样本资产在哪里；
- 下一阶段开发从哪里开始。

## 已确认的决策

1. HTML 是网站唯一发布物。
2. MD 是 Skill 生成的审计源文件，用于复查和重新生成，不参与网站上传、解析、预览或发布。
3. HTML 与对应 MD 都纳入 Git。
4. 旧的 Markdown 解析架构不建立 `archive/`；提取仍有价值的内容后删除，由 Git 历史负责追溯。
5. 只整理 `doc/` 及其必要依赖。项目根目录重复的哔哩哔哩 HTML/MD 不处理。
6. 为保持原型有效，可以同步修改 `tests/prototype.test.mjs`。
7. `docs/superpowers/specs/` 和 `docs/superpowers/plans/` 是实施历史，不改写旧路径，也不作为当前开发入口。

## 目标目录

```text
doc/
├── README.md
├── DEVELOPMENT.md
├── PRODUCT_UI.md
├── BACKEND.md
├── DEPLOYMENT.md
├── SEO.md
├── prototype.html
└── snapshots/
    ├── published/
    │   ├── 贵州茅台.html
    │   └── 哔哩哔哩.html
    └── sources/
        ├── 贵州茅台.md
        └── 哔哩哔哩.md
```

`prototype.html` 保留现有地址，避免改变用户当前预览入口。样本资产进入专用目录，发布物与源文件明确分开。

## 文档职责

### `README.md`

`doc/` 的唯一入口，包含：

- 当前阶段与已完成能力；
- HTML 发布主线；
- 文档地图和阅读顺序；
- 原型打开方式；
- 样本资产说明；
- 下一阶段开发入口；
- 当前文档与历史实施记录的优先级。

### `DEVELOPMENT.md`

当前产品与工程总纲，包含：

- 产品目标和首版范围；
- Vue、Nuxt、Vite、TypeScript、FastAPI、PostgreSQL、Nginx 与 Docker 技术栈；
- 公开端、管理端、API、数据库和文件存储的边界；
- HTML 发布数据流；
- 项目目标目录；
- 实施顺序、开发约定和测试层级。

它不重复具体页面、接口字段或部署命令，只链接到专题文档。

### `PRODUCT_UI.md`

合并当前有效的页面设计，包含：

- 公开首页的公司目录与 HTML 阅读工作区；
- 搜索、市场筛选、排序和空状态；
- 桌面左右结构与移动端公司抽屉；
- 独立快照地址；
- 管理端登录、HTML 导入、审核、预览、发布和撤回；
- 加载失败、无效 HTML 和发布阻断；
- 可访问性、焦点管理和响应式规则。

### `BACKEND.md`

合并 API 与数据库设计，包含：

- 认证与管理员会话；
- HTML 上传或目录扫描；
- 文件安全、元数据和可访问性校验；
- 草稿、已发布、已撤回和校验失败状态；
- 公司与快照索引；
- 文件路径、哈希、发布事务和审计日志；
- 公开接口和管理接口；
- 错误响应、幂等、并发、限流和 OpenAPI。

数据库保存元数据、路径、哈希、状态和审计记录，不保存 HTML 正文。MD 不进入后端内容流程。

### `DEPLOYMENT.md`

保留仍有效的 Docker 与阿里云设计，改为 HTML 内容模型，包含：

- Nginx、Nuxt、管理端、FastAPI 和 PostgreSQL 服务关系；
- 本地 Compose 与生产 Compose；
- 阿里云 ECS、`www.ayaseeri.com`、HTTPS 和安全组；
- HTML 内容卷、缓存、备份和恢复；
- 发布、回滚、健康检查、日志和告警。

### `SEO.md`

修正旧文档对 SSR Markdown 正文的假设，明确：

- iframe 外壳不等于可索引正文；
- 搜索引擎应索引独立 HTML 发布地址；
- 公开工作区和独立 HTML 的 canonical 边界；
- title、description、Open Graph、结构化数据、sitemap 和 robots 规则；
- 管理端和草稿禁止索引。

## 文件迁移与删除

| 现有文件 | 结果 |
|---|---|
| `DEVELOPMENT.md` | 按 HTML 主线改写 |
| `PAGE_MAIN.md` | 有效内容并入 `PRODUCT_UI.md`，原文件删除 |
| `PAGE_SEARCH.md` | 有效内容并入 `PRODUCT_UI.md`，原文件删除 |
| `PAGE_SNAPSHOT.md` | 有效内容并入 `PRODUCT_UI.md`，原文件删除 |
| `PAGE_ADMIN.md` | 有效内容并入 `PRODUCT_UI.md`，原文件删除 |
| `API_DESIGN.md` | 有效内容并入 `BACKEND.md`，原文件删除 |
| `DATABASE_DESIGN.md` | 有效内容并入 `BACKEND.md`，原文件删除 |
| `DOCKER.md` | 改写为 `DEPLOYMENT.md`，原文件删除 |
| `SEO.md` | 按 HTML 发布和独立地址重写 |
| `MARKDOWN_SPEC.md` | 提取 Skill 源文件边界后删除 |
| `prototype.html` | 保留地址，更新 manifest 路径 |
| 两份快照 HTML | 移入 `snapshots/published/` 并简化文件名 |
| 两份快照 MD | 移入 `snapshots/sources/` 并简化文件名 |

## 唯一内容主线

```text
Codex Skill
├── HTML → 网站唯一发布物
└── MD   → 审计、复查和重新生成的源文件

HTML
→ 管理端上传或扫描
→ 后端执行安全、元数据和文件可访问性校验
→ 人工审核
→ 发布
→ 公开端与管理端预览同一份 HTML
```

网站不得把 MD 作为运行时回退格式。MD 缺失不阻断网站，但应在资料维护流程中提示可追溯性不足。

## HTML 校验与错误处理

HTML 发布物必须：

- 是完整 HTML 文档；
- 包含非空 title，以及公司名称和代码；
- 自包含样式和内容；
- 不加载远程脚本、样式、图片或其他资源；
- 不包含可提交表单、危险导航或其他越权行为；
- 能在 sandboxed iframe 中阅读；
- 通过文件存在性和可访问性检查。

管理端预览与公开端使用相同文件、路径和 sandbox 规则。文件缺失、HEAD 失败、iframe 加载失败或安全校验失败时：

- 记录审核错误；
- 不保留失败 iframe；
- 禁止发布或重新发布；
- 提供明确错误信息和重新校验入口。

## 原型样本与生产存储

`doc/snapshots/` 保存当前原型的可复现样本，属于 Git 资产：

- `published/` 中的 HTML 被 `prototype.html` 直接读取；
- `sources/` 中的 MD 只用于审计与再生成；
- 两者都必须纳入版本控制。

正式后端的草稿、发布物和持久化内容卷属于后续实现。生产存储不得直接复用 `doc/snapshots/`，以免把文档样本和运行数据混在一起。

## 引用与范围

需要同步更新：

- `doc/prototype.html` 中的 HTML manifest；
- `tests/prototype.test.mjs` 中的路径和资产校验；
- 新的当前主线文档之间的链接。

不更新：

- 项目根目录的重复哔哩哔哩文件；
- 历史 specs 和 plans 中记录的旧路径。

## 验收标准

1. `doc/README.md` 能说明当前状态、唯一数据流、阅读顺序和下一阶段入口。
2. 当前文档不再宣称 Markdown 是网站事实来源，也不再描述上传或解析 Markdown。
3. 当前文档职责不重叠，内部链接全部有效。
4. `doc/prototype.html` 仍可从原地址打开。
5. manifest 只指向 `snapshots/published/贵州茅台.html` 和 `snapshots/published/哔哩哔哩.html`。
6. 两份 HTML 和两份 MD 均已纳入 Git；MD 不被运行时代码读取。
7. HTML 资产继续通过标题、自包含资源和危险能力检查。
8. 运行时测试继续覆盖撤回、重新发布、404、重新校验和 iframe 清理。
9. 根目录重复文件未修改。
10. 完整测试与 `git diff --check` 通过。

## 实施边界

本次只整理文档、移动样本资产并修正必要的原型与测试路径，不实现 Nuxt、管理端、FastAPI、数据库或 Docker 代码。任何生产架构细节如果尚未进入当前原型，应明确标注为目标设计，不伪装成已实现能力。
