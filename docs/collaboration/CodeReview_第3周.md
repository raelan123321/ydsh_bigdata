# Code Review 记录 · 第 3 周

> 评审对象：`feature/week3-dws-ads-nl2sql` 分支全部变更
> 评审方式：提交后逐文件通读 + 实跑验证（Hive 3.1.3 / Tez） + 脚本自测（`--source csv` 与 `--source hive` 双向）
> 评审角色：本人（开发）→ 本人（评审），按"先看口径、再看正确性、最后看可维护性"三轮进行
> 结论：**8 项问题，全部已修复并验证**；3 项转为 Issue（见 `Issue记录_第3周.md`）

## 一、问题清单

| # | 严重度 | 文件 | 问题 | 处理 | 验证 |
|---|---|---|---|---|---|
| CR-01 | 高 | `python/nl2sql/prompts.py` | Prompt 规则"字段别名用中文"导致生成的 SQL 在 Hive 3.1.3 报 `ParseException: cannot recognize input near 'as' ','`，10 条用例全部失败 | 改为"别名用英文小写；确需中文必须用反引号包裹"，5 个 few-shot 同步改写 | 重跑评测 10/10 可执行 |
| CR-02 | 高 | `sql/ads/11_kpi.sql` | 5 路 UNION ALL 各扫一次事实表，Tez 报 `Too many counters: 121 max=120`；`set tez.counters.max` 在 3.1.3 不存在，调参无效 | 重构为"单次扫描落 `ads_kpi_base` / `ads_kpi_base_user` 小表，再 UNION 展开 5 行"，扫描次数 5→2 | 重跑成功，KPI 5 行输出正常 |
| CR-03 | 中 | `sql/dwd/08_dwd_supplement.sql` | 第 2 周 `dwd_order` 直接将 12 种原始状态写入，KPI 若直接过滤会漏掉 `完成`/`已付款` 等同义值 | 新增 `dwd_order_norm` 做状态与渠道标准化（6 状态 / 4 渠道）后再算指标 | 标准化后状态剩 6 值、渠道 4 值，"其他"751 单 |
| CR-04 | 中 | `python/gmv_forecast.py` | 周粒度预测时，未来日期仍按 `+1 天` 递增，导致 4 个"周"落在连续 4 天，预测值从 44 万跌到 2 万 | `forecast()` 增加 `freq` 参数，按 7 天步长外推 | 重跑输出 12-30 / 01-06 / 01-13 / 01-20，数值平稳 |
| CR-05 | 中 | `python/ai_insight.py` | `build_report` 用 `attrib.get("target")` 判断，而 `main` 写入的键是 `target_date`，归因章节恒为空 | 统一为 `target_date` | 报告输出完整归因表（PC官网 +38.5% 等） |
| CR-06 | 中 | `python/ai_insight.py` | 周环比检测把跨年残周（2025-W01 仅 1 天数据）与完整周比较，误报"骤降 70%" | 只比较 `days >= 7` 的完整周 | 重跑后误报消失（0 条） |
| CR-07 | 低 | `python/gmv_forecast.py` | 缺少"均值基线"，导致线性回归以 9,840 的 MAE"胜出"，掩盖了模型无信号的事实 | 增加均值基线，并补充 R² 指标 | 均值基线 MAE 9,666 最优，结论改为"无预测力" |
| CR-08 | 低 | `python/gmv_forecast.py` | `Series.dt.dayofweek` 在 pandas 3 已弃用，产生警告 | 改为 `dt.day_of_week` | 警告消除 |

## 二、逐文件评审要点

### `sql/dwd/08_dwd_supplement.sql`
- 明细清洗条件 `quantity between 1 and 20 and unit_price > 0 and discount between 0 and 1` 合理，但要说明 **20 的上界是业务假设**（避免 99 这类异常），已在注释中标注。
- 明细表通过 `join dwd_order` 过滤，天然完成"只保留已入事实表的订单"，同时起到去重作用 —— 通过。
- 风险：若后续订单表增量加载，明细表需同步增量，否则会漏单。已转 Issue #5。

### `sql/dws/09_dws_agg.sql`
- 六张表全部基于 `dwd_order_norm`，口径一致 —— 通过。
- 周汇总用 `date_sub(next_day(order_date,'MO'),7)` 求周一，跨年周（2024-12-30 属 2025-W01）会落到 2024-12-30，`year_week` 用 `year()` 与 `weekofyear()` 拼接，出现 "2024-01" 与 "2025-01" 混排的可能 —— 属可接受偏差，已在 ADS 中不使用 `year_week` 做展示。
- `dws_category_day` 关联了 `dwd_order_norm` 只为过滤有效订单，代价是多一次 join；可接受（明细表无状态字段）。

### `sql/ads/10_ads_tables.sql`
- `ads_category_top10` 用 `row_number()` + 窗口累计求 `cum_share`，逻辑正确；但 `limit 10` 写在最外层，若品类少于 10 个则返回实际数量（本次 8 个）—— 通过。
- RFM 的 `ntile(5)` 在重复值较多时分组可能不均（如 frequency 大量相同），本次数据分布分散，未见问题；已注释说明。
- `datediff('2024-12-31', max(order_date))` 把观察期固定在年末，若数据范围变化需同步修改 —— 已转 Issue #6。

### `python/nl2sql/`
- `guard()` 的禁用词正则包含 `overwrite`，会误伤 `insert overwrite`（本就该拦）与注释中的词；已确认无误伤正常 SELECT。
- 自动补 `limit 200` 对聚合查询也生效，虽无副作用但会让结果行数受限；聚合结果远小于 200，实际无影响。
- `schema_extractor` 的 `desc` 解析在遇到 partition 段时用 `dtype is None` 截断，实测 16 张表全部解析正确 —— 通过。
- 安全：`.env` 已加入 `.gitignore`，仓库只保留 `.env.example` —— 通过。

### `python/ai_insight.py`
- 归因基准用"前 7 天日均"，若目标日恰在月初会跨月，属可接受近似。
- 品类归因金额与 GMV 不同口径，代码无法自动纠正，已在报告里加显式提示 + 口径一致性校验 —— 通过（这是"把限制写进产品"而不是"假装没有"）。

## 三、评审结论

- 阻断项（高）：2 项，均已修复并复测。
- 非阻断项：6 项，均已修复。
- 遗留：3 项转为 Issue，不影响本次交付。
- 总体评价：SQL 分层与口径清晰、脚本可重复执行、Python 侧具备降级能力（无 Hive 也能跑）；主要短板在"文档与代码的口径一致性维护"，建议后续把口径写进单一字典文件，由 SQL 注释、Prompt、文档共同引用。
