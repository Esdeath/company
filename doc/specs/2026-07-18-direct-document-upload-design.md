# 资料直接上传与 Markdown 渲染设计

> 状态：等待书面复核。确认后，本设计将取代现有文档中的 HTML 校验、人工审核和发布状态机方案。

## 目标

管理员先选择或新建公司，再把 Skill 生成的 HTML 或 Markdown 加入资料库。系统接收不同 Skill 的输出，不要求统一的业务字段，也不审核正文。

## 已确认的决定

- HTML 和 Markdown 都可上传。
- HTML 保留原文件，公开端直接嵌入。
- Markdown 保留原文件，并在上传时生成展示 HTML。
- 所有 Markdown 共用“现代编辑”模板。财报、访谈、演讲和其他资料依靠标题、段落、引用、列表及表格组织内容。
- 上传成功后资料立即公开。首版没有草稿、审核、发布、撤回或内容去重。

## 上传流程

1. 管理员选择或新建公司。
2. 管理员选择一个或多个 `.html`、`.md` 文件。
3. FastAPI 按扩展名保存文件。HTML 不转换；Markdown 套用统一模板生成 `rendered.html`。
4. 系统从 HTML `<title>` 或 Markdown 第一个一级标题取得展示标题；缺失时使用文件名。
5. FastAPI 写入资料索引。公开端随后可以读取该资料。

系统只处理文件无法读取、写入失败、Markdown 渲染失败和不支持的扩展名。系统不检查文档内容、远程资源、脚本、业务元数据或重复资料。

## 文件与索引

```text
content/companies/<company-id>/<document-id>/source.html
content/companies/<company-id>/<document-id>/source.md
content/companies/<company-id>/<document-id>/rendered.html
```

资料索引保存 `id`、`company_id`、`title`、`format`、`source_path`、`rendered_path`、`original_filename` 和 `uploaded_at`。路径使用系统生成的 ID。同名文件会产生两条记录，管理员可以重命名或删除。

## 展示方式

公开端保留公司目录和阅读区。用户选择公司后可以浏览该公司的资料列表，再打开一份资料。HTML 原文件与 Markdown 生成页都由同一个 iframe 阅读器加载。iframe 保留隔离用的空 `sandbox`；系统不根据内容决定是否展示。

Markdown 模板支持标题、段落、强调、引用、列表、任务列表、表格、图片、链接、脚注、分隔线和代码块。长表格可以横向滚动，图片不超出正文，正文宽度适合手机阅读。模板升级时，后台可以从 `source.md` 批量重新生成 Markdown 展示页；HTML 原文件不变。

## 失败处理

FastAPI 先写临时文件，完成渲染和索引写入后再移动到最终目录。任一步失败时，FastAPI 删除本次临时文件并返回错误，不保留残缺记录。批量上传按文件返回结果，一个文件失败不撤销其他已成功文件。

## 验收范围

- HTML 上传后保持原字节并能在阅读器中打开。
- Markdown 上传后保留源文件并产生展示 HTML。
- 标题提取与文件名回退有效。
- 财务快照、CEO 访谈和公开演讲示例使用同一模板。
- 表格、引用、列表、链接、图片和手机布局可读。
- 模板批量重新生成不会修改源 Markdown。

## 首版不做

首版不做内容安全校验、元数据契约、SHA-256 门禁、人工审核、发布状态机、Skill 身份识别、自动分类和正文搜索。
