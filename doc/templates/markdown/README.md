# 通用 Markdown 模板

这套模板用于网站中的 Markdown 资料。财务快照、CEO 访谈、公开演讲和其他研究资料共用同一版式。

## 文件

- `template.html`：FastAPI 渲染时使用的页面外壳。
- `template.css`：标题、正文、引用、列表、表格、图片和代码块样式。
- `showcase.html`：三类资料的交互预览。
- `examples/`：财务快照、CEO 访谈和公开演讲的 Markdown 示例。

## 模板变量

`template.html` 使用三个占位符：

- `{{ document_title }}`：第一个一级标题，缺失时使用文件名。
- `{{ document_meta }}`：可选的公司名、来源或上传时间文字。
- `{{ document_content }}`：Markdown 转换后的 HTML。转换器应从正文中移除已作为页面标题使用的第一个一级标题。

模板不要求 Front Matter 或资料类型。后端保存原始 Markdown，并把渲染结果保存为 `rendered.html`。模板调整后，后台可以重新生成这些展示文件。

直接打开 [showcase.html](./showcase.html) 可以比较同一模板下的三种资料。
