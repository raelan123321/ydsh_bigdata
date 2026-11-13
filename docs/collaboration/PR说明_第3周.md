# Pull Request 说明 · 第 3 周（DWS/ADS + KPI + 预测 + NL2SQL + AI 洞察）

> 分支：`feature/week3-dws-ads-nl2sql` → `main`
> 提交范围：`2cfcf92..HEAD`（共 9 个提交，每个子任务独立提交）
> 说明：本项目为个人独立完成，无第二协作账号，GitHub 上未创建真实 PR。
> 为满足"PR / Code Review / Issue 留痕"要求，按团队规范在仓库内保留 PR 描述、自审记录与 Issue 清单，
> 评审流程与真实 PR 一致（提交前自审、逐条核对、问题转 Issue）。若后续有队友，可直接复用本模板发起真实 PR。

## 一、变更内容

| 子任务 | 变更文件 | 说明 |
|---|---|---|
| 1 数仓补齐 | `sql/dwd/08_dwd_supplement.sql` | 补 `dim_store`；建订单明细清洗表；订单状态/渠道标准化落 `dwd_order_norm` |
| 1 DWS | `sql/dws/09_dws_agg.sql` | 天/周/月/品类/门店/渠道 六张汇总表 |
| 1 ADS | `sql/ads/10_ads_tables.sql` | 销售日报（环比+MA7）、品类 Top10（含累计占比）、RFM 用户分层 |
| 1 KPI | `sql/ads/11_kpi.sql` | 5 项 KPI 结果表 + 月度趋势（含复购率） |
| 2 预测 | `python/gmv_forecast.py` | 均值/MA7/线性回归三模型对比，日+周两种粒度，时间序列留出验证，MAE/RMSE/MAPE/R² |
| 3-4 NL2SQL | `python/nl2sql/*` | Schema 抽取（含缓存）、Prompt（规则+5 示例）、LangChain/OpenAI 双后端、SQL 安全闸门、10 题评测 |
| 5 AI 洞察 | `python/ai_insight.py` | 异常检测（z-score/周环比/品类漂移）、渠道与品类贡献度归因、自动成文、口径一致性校验 |
| 交付物 | `交付数据/*`、`docs/*.docx`、`output/week3/*` | KPI 结果表（CSV+XLSX）、两份文档、实跑结果记录 |

## 二、口径变更（需评审确认）

1. **新增有效订单过滤**：`order_status in ('已完成','已支付') and pay_amount is not null`。
   影响：GMV 由上版（未过滤）3,611.67 万变为 **2,329.05 万**，下降 35.5%。这是口径修正，不是数据丢失。
2. **状态数字码归入"其他"**：1/2/3/4 共 751 单（5.0%）无法还原语义，排除出 KPI。**需业务方提供码表**（见 Issue #1）。
3. **复购率改用月度口径展示**：年度复购率 100% 无区分度（见 Issue #3）。

## 三、验证情况

| 验证项 | 方式 | 结果 |
|---|---|---|
| SQL 可执行 | 在 Hive 3.1.3 实跑 08→09→10→11 | 全部成功，16 张表行数与预期一致 |
| KPI 正确性 | 与独立 SQL 交叉比对 | 5 项指标一致（GMV 23,290,536.89 / 9,236 单 / AOV 2,521.71） |
| 预测建模 | 时间序列留出验证（末 14 天） | 三模型 R² ≤ 0，结论为"无信号"，已写入边界分析 |
| NL2SQL | 10 题评测（离线规则链路） | 可执行 10/10，一致 10/10（**不代表 LLM 准确率**） |
| AI 洞察 | 自动生成报告并与源数据核对 | 13 条异常、1 个归因案例、3 项数据质量问题 |

## 四、自审清单

- [x] 所有 SQL 使用全库名，无隐式默认库依赖
- [x] DWS/ADS 表均 `drop table if exists` 后再建，脚本可重复执行
- [x] 指标口径在脚本注释、文档、Prompt 三处保持一致
- [x] 无硬编码密码（`.env.example` 提供模板，`.env` 已 gitignore）
- [x] Python 脚本支持 `--source hive|csv`，无 Hive 环境也可复现
- [x] 未提交中间产物（`output/brief-compose/*.html` 已在 .gitignore）
- [x] 文档中的每个数字都能在 `output/week3/实跑结果记录.md` 找到出处

## 五、已知问题（不阻塞合并）

1. NL2SQL 大模型链路未实测（无 API Key），只验证了离线链路与 SQL 合法性 → Issue #4
2. 品类金额与 GMV 不勾稽，品类指标仅可做结构分析 → Issue #2
3. XGBoost 未参与对比（环境未安装，代码已留接口）

## 六、合并后待办

- 补上游"订单金额 = 明细金额之和"勾稽校验（Issue #2）
- 向业务方索取订单状态码表（Issue #1）
- 配置 LLM Key 后跑同一套评测脚本，得出 LLM 口径准确率（Issue #4）
