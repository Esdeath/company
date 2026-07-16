# 企业快照 Markdown 规范

## 设计目标

Markdown 是快照正文的唯一事实来源。Skill、人工整理流程和网站只要遵守本规范，就可以独立演进。

## 文件生命周期

```text
content/inbox/
→ content/drafts/{market}/{ticker}/{data_as_of}.md
→ content/published/{market}/{ticker}/{data_as_of}.md
```

- `inbox`：可选的服务器待扫描目录。
- `drafts`：校验通过、尚未公开的文件。
- `published`：已公开文件。
- 上传文件先进入临时目录，校验完成后原子移动到 `drafts`。
- 发布和撤回都通过原子移动完成。

最终路径由已校验的字段计算，不使用原始文件名。

## 编码和大小

- 文件扩展名：`.md`。
- 编码：UTF-8，无 BOM 或有 BOM 都可读取，保存时统一无 BOM。
- 最大文件：2 MiB。
- 换行：保存时统一 LF。
- 禁止 NUL 字符。
- 禁止符号链接和越界路径。

## Frontmatter

文件以 YAML frontmatter 开始：

```yaml
---
schema_version: 1
type: value_snapshot
title: 腾讯控股价值快照
company_name: 腾讯控股
ticker: "00700"
market: HK
exchange: HKEX
reporting_currency: CNY
quote_currency: HKD
data_as_of: 2025-12-31
generated_at: 2026-07-16T10:30:00+08:00
generator: hk-value-snapshot
status: draft
verdict: second_round
summary: 现金流和资产负债表稳健，估值需要结合增长持续性继续验证。
metrics:
  price: 482.40
  pe_ttm: 18.2
  pb: 3.4
  dividend_yield_pct: 2.1
  market_cap_million: 4450000
source_urls:
  - https://example.com/annual-report
  - https://example.com/quote
---
```

## 字段定义

| 字段 | 类型 | 必填 | 规则 |
|---|---|---|---|
| `schema_version` | integer | 是 | 首版固定为 `1` |
| `type` | string | 是 | 固定为 `value_snapshot` |
| `title` | string | 是 | 1–120 字符 |
| `company_name` | string | 是 | 1–100 字符 |
| `ticker` | string | 是 | 始终使用字符串 |
| `market` | enum | 是 | `CN` 或 `HK` |
| `exchange` | enum | 是 | `SSE`、`SZSE` 或 `HKEX` |
| `reporting_currency` | string | 是 | ISO 4217 货币代码 |
| `quote_currency` | string | 是 | ISO 4217 货币代码 |
| `data_as_of` | date | 是 | 财务数据截止日 |
| `generated_at` | datetime | 是 | 含时区的 ISO 8601 |
| `generator` | string | 是 | 生成工具名称 |
| `status` | enum | 是 | `draft` 或 `published`；上传时必须为 `draft` |
| `verdict` | enum | 是 | `second_round` 或 `skip` |
| `summary` | string | 是 | 1–120 个中文字符或等价长度 |
| `metrics` | object | 否 | 只保存展示所需快照指标 |
| `source_urls` | URL[] | 是 | 至少一个 `https` 来源 |

未知顶层字段在 schema version 1 中触发警告，不直接丢弃。保留这些字段可以避免未来版本导入时静默损失数据。

## 市场和代码规则

### A 股

- `market: CN`。
- 上海证券交易所使用 `exchange: SSE`。
- 深圳证券交易所使用 `exchange: SZSE`。
- `ticker` 必须是六位数字字符串。

### 港股

- `market: HK`。
- `exchange: HKEX`。
- `ticker` 保存为五位数字字符串，例如 `00700`。
- 输入 `700` 时允许标准化为 `00700`，并生成信息级校验提示。

市场与交易所组合不匹配时属于错误。

## 正文结构

一级标题只出现一次。五个主章节名称和顺序固定：

```markdown
# 腾讯控股价值快照

## 一、入口检验

## 二、五步扫描

## 三、5 秒心算

## 四、五问清单

## 五、资料来源
```

章节下的小标题可以随 Skill 迭代，但不能删除五个主章节。

## 事实、判断和待验证项

正文应明确区分三类内容。推荐格式：

```markdown
> [事实]
> 2025 年经营现金流为……，来源见文末链接 1。

> [判断]
> 现金流质量通过第一轮检查，但仍需核对资本化支出。

> [待验证]
> 需查阅附注确认其他应收款的主要对手方。
```

- 事实必须能追溯到公开来源或由公开数字直接计算。
- 直接计算要写出公式或口径。
- 判断不能伪装为公司披露事实。
- 无法核实的内容进入待验证项，不能补猜测数字。

## 资料来源

正文最后一节至少列出：

- 来源名称。
- 报告期或行情日期。
- URL。
- 访问日期。

示例：

```markdown
1. 腾讯控股 2025 年年度报告，报告期 2025-12-31，
   https://example.com/report，访问于 2026-07-16。
```

`source_urls` 用于机器校验和页面元数据，正文来源列表用于读者理解。两者必须覆盖相同的核心来源，但顺序不要求一致。

## Markdown 功能边界

允许：

- 标题、段落、强调、列表和引用。
- GFM 表格。
- 代码和行内代码。
- `https` 链接。

禁止：

- 原始 HTML。
- JavaScript URL。
- iframe、表单和脚本。
- 本地绝对路径。
- Data URL 和内嵌 Base64 文件。

首版不托管图片。如果文档中出现远程图片语法，校验器给出错误。后续启用图片时再扩展 schema 和安全策略。

## 校验级别

### 错误

- YAML 无法解析。
- 必填字段缺失或类型不符。
- 市场、交易所和代码冲突。
- 缺少固定正文章节。
- 文件超限或存在危险内容。
- 同一 `(market, ticker, data_as_of)` 已存在且未明确覆盖。

### 警告

- 未知 frontmatter 字段。
- 可选指标缺失。
- 来源 URL 重复。
- 摘要接近长度上限。
- 存在判断但没有相邻事实或来源。

### 信息

- 代码被补零或标准化。
- 换行和 BOM 被规范化。

## 重复和覆盖

快照唯一键为：

```text
(market, ticker, data_as_of)
```

- 上传同一版本默认返回冲突，不自动覆盖。
- 管理员可以显式选择替换草稿。
- 已发布版本不能直接覆盖，必须先撤回。
- 替换文件后重新计算 SHA-256，并写入审计记录。

发布时 content service 把 frontmatter 的 `status` 改为 `published`，重新计算哈希，再原子移动文件。撤回时改回 `draft`。这两次改写都记录在审计日志中，其他 frontmatter 和正文保持不变。

## Skill 输出约定

`hk-value-snapshot` 可以分别使用 A 股和港股数据适配器，但最终输出必须相同：

```text
输入公司名称或代码
→ 识别市场和交易所
→ 获取公开数据
→ 统一字段和单位
→ 生成 Markdown
→ 按本规范自检
```

Skill 生成的 HTML 只用于本地查看，网站不导入 HTML。

## 版本升级

修改必填字段、正文主结构或字段语义时，必须增加 `schema_version`。API 至少保留对上一版本的只读解析能力，并通过迁移工具生成新文件，不在读取时静默改写已发布 Markdown。
