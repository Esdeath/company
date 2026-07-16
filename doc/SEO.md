# SEO 设计

## 目标

让公司快照详情页可被搜索引擎稳定抓取，同时不牺牲真实用户的阅读体验。公开页面由 Nuxt SSR 输出完整 HTML，不根据 User-Agent 返回两套内容。

## 页面策略

| 页面 | 索引策略 | 说明 |
|---|---|---|
| `/` | `index,follow` | 产品入口和最新快照 |
| `/search` | 默认 `noindex,follow` | 查询组合多，避免低价值重复页 |
| `/snapshots/:market/:ticker` | `index,follow` | 公司最新快照规范页 |
| `/snapshots/:market/:ticker/:date` | `index,follow` | 有独立研究价值的历史版本 |
| `/admin/*` | `noindex,nofollow` | 管理页面 |
| `/api/*` | 不生成 HTML | API |

## 页面元数据

### 首页

```text
title: 企业快照库｜A股与港股财务快照
description: 基于公开财报与行情整理的 A 股、港股企业价值快照，用于快速筛选和长期研究。
canonical: https://www.ayaseeri.com/
```

### 最新快照

```text
title: 腾讯控股（00700）企业价值快照｜数据截至 2025-12-31
description: {summary}
canonical: https://www.ayaseeri.com/snapshots/HK/00700
```

### 历史版本

```text
title: 腾讯控股（00700）企业价值快照｜2025-12-31
canonical: https://www.ayaseeri.com/snapshots/HK/00700/2025-12-31
```

description 移除 Markdown 标记并限制在约 120 个中文字符。不得自动添加“值得买入”等原文不存在的判断。

## Canonical 和重定向

- 根域 `ayaseeri.com` 301 到 `www.ayaseeri.com`。
- 市场使用大写规范值 `CN`、`HK`。
- 港股代码补足五位，A 股补足六位。
- 非规范 URL 301 到规范 URL。
- 不带日期的公司页 canonical 指向自身，不指向当前日期 URL。
- 历史版本 canonical 指向自身。
- 查询参数不进入 canonical。

## Open Graph

所有可索引页面输出：

- `og:type=article` 用于快照页，首页使用 `website`。
- `og:title`。
- `og:description`。
- `og:url`。
- `og:site_name=企业快照库`。
- 默认分享图；后续可以按公司生成，不作为 MVP 阻塞项。

同时输出 Twitter Card 的 summary large image 字段。

## 结构化数据

详情页使用 `Article`，不能使用暗示实时证券报价的类型：

```json
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "腾讯控股（00700）企业价值快照",
  "datePublished": "2026-07-16T10:30:00+08:00",
  "dateModified": "2026-07-16T10:30:00+08:00",
  "about": {
    "@type": "Organization",
    "name": "腾讯控股",
    "identifier": "HKEX:00700"
  },
  "isBasedOn": ["https://example.com/annual-report"],
  "mainEntityOfPage": "https://www.ayaseeri.com/snapshots/HK/00700/2025-12-31"
}
```

如果作者和站点主体尚未确定，不输出虚假的 `author` 或 `publisher.logo`。

## Sitemap

提供 `/sitemap.xml`：

- 包含首页。
- 包含所有已发布的最新公司页。
- 包含所有仍公开的历史版本。
- 撤回后从 sitemap 删除。
- `lastmod` 使用发布时间或最后一次公开内容变更时间，不使用每次请求时间。
- 单个 sitemap 超过 50,000 URL 时拆分，MVP 暂不需要。

Nuxt 通过公开 API 或构建时服务生成 sitemap，不直接读取数据库和磁盘。

## robots.txt

```text
User-agent: *
Allow: /
Disallow: /admin/
Disallow: /api/
Sitemap: https://www.ayaseeri.com/sitemap.xml
```

robots.txt 不是权限控制。管理端和 API 仍必须正常认证。

## 内容输出

- 首次 HTML 已包含公司名称、摘要、指标和完整 Markdown 正文。
- 标题层级从一个 `h1` 开始，主章节使用 `h2`。
- 来源链接保留可读名称。
- 表格在 HTML 中有表头语义。
- 图片后续启用时必须有 alt；MVP 不接收图片。
- 页面包含数据截止日和生成时间，避免把历史数据误解为实时数据。

## 搜索页

搜索页默认 `noindex,follow`。以下参数不生成可索引落地页：

- 任意关键词 `q`。
- 游标 `cursor`。
- 排序 `sort`。
- 市场筛选 `market`。

如果未来市场分类页内容充足，可以新增 `/markets/cn` 和 `/markets/hk`，而不是开放查询参数索引。

## 性能要求

SEO 与性能共用目标：

- 服务端尽量在 800 ms 内返回首字节。
- LCP 目标小于 2.5 秒。
- CLS 目标小于 0.1。
- 首屏不依赖客户端请求才能看到正文。
- 字体优先使用系统字体，避免阻塞下载。
- 静态资源使用内容哈希和长期缓存。

## 发布检查

每次发布至少检查：

1. 查看页面源代码，确认正文已 SSR。
2. title、description、canonical 与页面版本一致。
3. JSON-LD 可解析且不包含草稿数据。
4. sitemap 只含已发布内容。
5. 管理端带 `noindex`。
6. 非规范代码和根域跳转使用 301。
7. 404 页面返回真实 404 状态码。
8. TLS 证书有效且覆盖根域和 www。

## 内容边界

网站是研究资料库，不宣称提供投资建议。页脚和快照详情显示简短声明：

> 内容基于公开资料整理，仅供研究参考，不构成投资建议。财务数据以公司正式披露为准。

声明不能替代准确引用和数据日期，也不能用于掩盖未经核实的内容。
