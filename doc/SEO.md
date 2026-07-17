# SEO 设计

## 当前原型限制

当前 `doc/prototype.html` 是交互原型：公开工作区用 iframe 展示本地快照样本。iframe 外壳可以说明产品、公司目录和阅读入口，但不能让搜索引擎把嵌入的快照文本可靠地当作外壳页面的可索引正文。原型也没有真实路由、发布状态、服务端元数据、sitemap 或撤回同步。

生产目标因此不把 iframe 当作 SEO 正文载体。iframe 只用于隔离阅读和管理预览；每个通过校验并处于已发布状态的快照都必须另有稳定、可直接请求的独立页面。

## 可索引页面

| 页面 | 目标策略 | 说明 |
|---|---|---|
| `/` | `index,follow` | 产品与公开目录入口，只索引外壳自身可见说明 |
| 独立历史 HTML | `index,follow` | 某公司某数据截止日的稳定发布物 |
| 最新公司捷径 | 跳转或显式 canonical | 解析到当前最新已发布版本 |
| 搜索结果和带查询参数页面 | 默认 `noindex,follow` | 避免大量重复组合 |
| iframe 工作区外壳 | `noindex,follow` 或 canonical 到独立页面 | 不声称包含可索引快照正文 |
| 草稿、撤回、无效内容 | `noindex,nofollow` 且不公开 | 公开请求返回 404 或 410 |
| `/admin/*`、受控预览 | `noindex,nofollow` | 同时要求认证和 `no-store` |
| `/api/*` | robots 阻止抓取 | API 不是搜索落地页 |

只有已发布内容可以出现在公开索引、站内目录和 sitemap。robots 或 `noindex` 不能替代认证与状态检查。

## 独立 HTML 发布地址

每条已发布快照获得稳定的独立 HTML 发布地址：

```text
https://www.ayaseeri.com/snapshots/{market}/{ticker}/{data_as_of}.html
```

例如：

```text
https://www.ayaseeri.com/snapshots/HK/00700/2025-12-31.html
```

该地址直接返回经验证的 HTML 发布物和真实 HTTP 状态，不要求先执行客户端脚本，也不依赖 iframe 才能读到内容。历史地址发布后保持稳定；撤回后从公开目录移除并返回 404 或按保留政策返回 410。

最新公司路由 `/snapshots/{market}/{ticker}` 是便利入口。它应 302/307 到当前最新独立 HTML；若产品决定直接返回内容，也必须把 canonical 指向当前版本的独立 HTML。市场和代码先规范化，非规范地址再跳转。

## 工作区与 canonical

- 根域 `ayaseeri.com` 301 到 `www.ayaseeri.com`。
- 每个历史独立 HTML 的 canonical 指向自身，且不含查询参数。
- 最新公司路由的 canonical 指向当时最新的独立 HTML；最新版本变化时同步更新。
- iframe 工作区若只包装某条快照，设置 `noindex` 并把 canonical 指向被展示的独立 HTML，不能把外壳声明为正文规范页。
- `CN`、`HK` 使用大写规范值；港股代码补足五位，A 股代码补足六位；其他拼写 301 到规范地址。
- 分页、搜索、筛选、预览 token、游标与跟踪参数不进入 canonical。

canonical 是去重提示，不是访问控制。撤回、草稿和无效记录不能仅靠 canonical 隐藏。

## 元数据

title、description、公司名、市场、证券代码、数据截止日、发布时间、来源摘要和 canonical 来自已通过校验的 HTML/index metadata。发布流程验证这些字段与文件哈希、记录版本一致；不从另一种源文件格式临时解析，也不自动生成原文没有的投资判断。

独立页面示例：

```text
title: 腾讯控股（00700）企业价值快照｜2025-12-31
description: {经过长度与内容校验的摘要}
canonical: https://www.ayaseeri.com/snapshots/HK/00700/2025-12-31.html
robots: index,follow
```

页面显示数据截止日和生成/发布时间，避免把历史财务数据理解为实时行情。不存在或未发布的记录返回真实 404，不能用 `200` 错误页面伪装。

## Open Graph 与结构化数据

所有可索引独立 HTML 输出一致的 Open Graph 与 Twitter Card 字段：`og:type=article`、`og:title`、`og:description`、`og:url`、`og:site_name` 和有效分享图。首页使用 `og:type=website`。

快照页可以输出 `Article` JSON-LD，包括 `headline`、`datePublished`、`dateModified`、公司 `about`、可靠来源和等于 canonical 的 `mainEntityOfPage`。未确定作者、发布主体或 logo 时不编造字段，也不使用暗示实时证券报价的类型。

结构化数据必须与用户看到的独立 HTML、索引元数据和发布状态一致。禁止按 User-Agent 返回不同正文，禁止 cloaking 或专供爬虫的页面。

## Sitemap 与 robots

sitemap 只包含已发布的独立 HTML；`/sitemap.xml` 不包含首页、iframe 工作区、搜索参数页、管理员、API、草稿、预览、无效或撤回记录。发布成功后加入；撤回事务完成后立即移除。`lastmod` 使用真实发布时间或最后一次公开内容变更时间。

```text
User-agent: *
Allow: /
Disallow: /admin/
Disallow: /api/
Disallow: /preview/
Sitemap: https://www.ayaseeri.com/sitemap.xml
```

robots.txt 只是抓取提示。管理端、API、预览和检查器端点仍必须通过网络边界、认证和授权保护；敏感 URL 还要返回 `X-Robots-Tag: noindex, nofollow`。

## 管理端、草稿与撤回

- 管理端页面始终输出 `noindex,nofollow` 和 `Cache-Control: no-store`，并要求有效 Session。
- 草稿和受控预览输出 `X-Robots-Tag: noindex, nofollow`，使用短时绑定 URL，不能出现在公开导航或 sitemap。
- 静态校验失败、可信加载检查失败或元数据无效的记录不得发布，公开请求返回 404。
- 撤回事务同时更新 PostgreSQL 状态、移出公开 HTML、使缓存失效并从 sitemap 删除；搜索引擎随后看到 404 或 410。
- API 响应不是落地页，不进入搜索索引；公开 API 只暴露已发布记录。

## 性能与发布检查

独立 HTML 首次响应就包含用户可读内容、标题层级、表格语义、来源链接和必要元数据。目标 LCP 小于 2.5 秒、CLS 小于 0.1；带哈希静态资源长期缓存，HTML 使用可撤回的明确缓存策略。

每次发布至少自动或人工检查：

1. 独立 HTML 地址无需脚本和 iframe 即可返回内容，状态码与 `Content-Type` 正确。
2. title、description、canonical、robots、Open Graph 与 JSON-LD 对应同一记录和版本。
3. 最新路由解析到正确历史版本，历史 canonical 指向自身。
4. sitemap 只含已发布独立 HTML，撤回记录已移除。
5. 管理端、草稿、预览、无效内容和 API 不可索引且不可被公开缓存。
6. 非规范域名、市场和代码按规则跳转；404/410 返回真实状态。
7. 页面没有 User-Agent 特供内容或 cloaking。
8. HTTPS 证书有效，移动端加载和核心性能指标符合目标。
