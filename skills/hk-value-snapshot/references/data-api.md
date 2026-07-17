# 数据接口参考(港股)

## 1. 年报主要财务指标 — 东方财富 F10

```
https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_HKF10_FN_MAININDICATOR&columns=ALL&filter=(SECUCODE%3D%22{代码}.HK%22)(DATE_TYPE_CODE%3D%22001%22)&sortColumns=STD_REPORT_DATE&sortTypes=-1&pageSize=12
```

- `{代码}` 为 5 位数字,如 `09992`、`01810`、`00700`。
- `DATE_TYPE_CODE`:001=年报,002=中报,003=一季报,004=三季报。快照只需年报;如需单季拆分再取累计报告期相减。
- URL 过长会被拒(HTTP 403 url_too_long),用 `columns=ALL` 而不要罗列字段名。
- 返回为 JSON,`result.data[]` 每元素一个报告期。

### 关键字段(财报数据为人民币)

| 字段 | 含义 | 注意 |
|---|---|---|
| REPORT_TYPE / STD_REPORT_DATE | 报告期 | |
| OPERATE_INCOME / OPERATE_INCOME_YOY | 营业收入 / 同比% | 单位:元 |
| HOLDER_PROFIT / HOLDER_PROFIT_YOY | 归母净利润 / 同比% | |
| GROSS_PROFIT / GROSS_PROFIT_RATIO | 毛利 / 毛利率% | |
| NET_PROFIT_RATIO | 净利率% | |
| BASIC_EPS / DILUTED_EPS / EPS_TTM | 每股收益 | 元 |
| BPS | 每股净资产 | 元 |
| PER_OI / PER_NETCASH_OPERATE | 每股营收 / 每股经营现金流 | 元 |
| ROE_AVG / ROE_YEARLY / ROIC_YEARLY | ROE(平均/年化) / ROIC | % |
| TOTAL_ASSETS / TOTAL_LIABILITIES / TOTAL_PARENT_EQUITY | 总资产/总负债/归母净资产 | 元 |
| DEBT_ASSET_RATIO / CURRENT_RATIO | 资产负债率% / 流动比率 | |
| PRETAX_PROFIT / TAX_EBT | 税前利润 / 实际税率% | EBIT≈税前+利息 |
| NETCASH_OPERATE / NETCASH_INVEST / NETCASH_FINANCE / END_CASH | 三大现金流 / 期末现金 | 融资现金流大额流入=配售/发债信号 |
| INVENTORY_TDAYS / ACCOUNTS_RECE_TDAYS | 存货/应收周转天数 | |
| DPS_HKD | **最新**年度股息(港元) | 所有行重复同一值,勿当历史 |
| DPS_HKD_LY | 该报告期上一年度股息 | 逐行串成历史股息序列 |
| DIVI_RATIO / DIVIDEND_RATE | 分红率 / 股息率 | null=未派息 |
| ISSUED_COMMON_SHARES / PER_SHARES | **当前**已发行股本 / 每手股数 | 历史股本须用 净利÷EPS 推算 |
| PE_TTM / PB_TTM | 按接口时点价的估值 | PE_TTM_SQ/PB_TTM_SQ 为上年同期,可作历史参照 |
| TOTAL_MARKET_CAP | 总市值(港元) | 接口时点价,与最新行情核对 |
| CURRENCY | 标注"HKD"但**财务数据实为人民币** | 已实测验证,勿被误导 |

## 2. 实时行情 — 腾讯

```
https://qt.gtimg.cn/q=hk{代码}
```

返回 `~` 分隔的字符串(GBK 编码,公司名可能乱码,不影响数字)。按位置解析(从 0 计):

- [3] 现价 · [4] 昨收 · [5] 今开
- [30] 形如 `2026/06/05 16:09:17` 的时间戳 —— **必须检查,常为缓存旧价,页面须如实标注该日期**
- [33]/[34] 52周内高/低附近字段;更稳妥的 52 周高低在串中形如 `61.450~27.500` 的相邻两值,用现价数量级交叉验证
- 总市值(亿港元)出现两次相邻(如 `5945.39~7183.49`,同股不同权公司前者为流通市值、后者为总市值;取与"总股本×现价"吻合的那个)
- 串尾附近有总股本(如 `25839890294.00`),与 F10 的 ISSUED_COMMON_SHARES 交叉验证

**校验习惯**:现价 × 总股本 ≈ 总市值;API 股息率 ≈ DPS_HKD ÷ 现价。两条都对上才可用。

## 3. 备选与失败处理

- F10 v1 接口失败时可试旧版:`https://datacenter.eastmoney.com/securities/api/data/get?type=RPT_HKF10_FN_MAININDICATOR&sty=...`(sty 参数易变,优先用 v1)。
- 行情备选:东财 `https://push2.eastmoney.com/api/qt/stock/get?secid=116.{代码}&fields=f43,f57,f58,f116,f162,f167&ut=fa5fd1943c7b386f172d6893dbfba10b&invt=2&fltt=2`(可能返回空,不稳定)。
- A股同类需求:主要财务指标接口为 `type=RPT_F10_FINANCE_MAINFINADATA&sty=APP_F10_MAINFINADATA`,行情 `qt.gtimg.cn/q=sh600519` / `q=sz000001`,字段体系不同(拼音缩写,TZ=同比,DJD=单季)。
- 汇率:估值折算固定用 1 RMB = 1.09 HKD,页尾注明;如需精确可另查当日汇率并改注。
