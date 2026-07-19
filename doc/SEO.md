# SEO 设计

## 索引目标

公开站点索引已建立索引的资料内容。HTML 原文件和 Markdown 生成页都需要稳定、可直接请求的内容地址；iframe 工作区只提供阅读体验，不把 iframe 外壳当成资料正文的索引载体。

## 可索引页面

| 页面 | 策略 | 说明 |
|---|---|---|
| `/` | `index,follow` | 产品与公开公司目录入口 |
| 单份资料内容地址 | `index,follow` | HTML 原文件或 Markdown 生成页 |
| 公司资料列表 | `index,follow` | 已建立索引的公司资料目录 |
| 搜索结果和带查询参数页面 | `noindex,follow` | 避免重复组合 |
| iframe 工作区外壳 | `noindex,follow` | 阅读入口不替代内容地址 |
| `/admin/*` | `noindex,nofollow` | 管理界面 |
| `/api/*` | robots 阻止抓取 | API 不是搜索落地页 |

## 内容地址与 canonical

每份资料拥有稳定地址。内容响应直接返回 HTML 原文件或 Markdown 生成页，不要求先执行客户端脚本，也不依赖 iframe 才能读取正文。canonical 指向该资料自己的无查询参数地址；公司列表和筛选页不把查询参数放进 canonical。

根域 `ayaseeri.com` 301 到 `www.ayaseeri.com`。市场和证券代码使用规范格式；非规范地址跳转到规范地址。

## 元数据

标题来自 HTML `<title>` 或 Markdown 第一个一级标题，缺失时使用原始文件名去掉扩展名后的文件名主体。description、公司名称、市场、证券代码、上传时间和 canonical 来自公司与资料索引。页面不编造投资判断或实时行情字段。

内容地址输出与页面可见内容一致的 Open Graph 和结构化数据。禁止按 User-Agent 返回不同正文，禁止 cloaking 或专供爬虫的页面。

## Sitemap 与 robots

sitemap 包含已建立索引的资料内容和需要收录的公司资料列表。`lastmod` 使用真实上传时间或最后一次重新生成 Markdown 展示页的时间。

```text
User-agent: *
Allow: /
Disallow: /admin/
Disallow: /api/
Sitemap: https://www.ayaseeri.com/sitemap.xml
```

robots.txt 只是抓取提示。管理端和 API 仍要由网络边界、认证和授权保护；管理页面返回 `X-Robots-Tag: noindex, nofollow` 和 `Cache-Control: no-store`。

## 性能与检查

内容地址首次响应就包含用户可读的标题、正文、表格语义和来源链接。带哈希的静态资源可以长期缓存；HTML 响应使用适合内容更新的缓存验证策略。每次部署检查内容地址、canonical、robots、sitemap、移动端阅读和 HTTPS 证书。
