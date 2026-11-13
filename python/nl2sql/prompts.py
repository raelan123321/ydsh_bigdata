"""
Prompt 模板：NL2SQL 的"知识注入"层
===================================
设计要点（答辩重点）
  1. 角色约束：只做"自然语言 -> Hive SQL"的翻译，不做解释性输出
  2. 硬规则前置：只允许 SELECT、必须带库名、销售指标必须走有效订单口径
  3. 优先用汇表层：能查 dws/ads 就不要 join 明细，减少生成错误的概率
  4. Few-shot 用真实表结构写：示例 SQL 全部在本项目实跑通过
  5. 输出格式锁定：只输出一段 ```sql 代码块，便于解析；解析失败可重试
"""

SYSTEM_PROMPT = """你是「云购生活」新零售数仓的 SQL 助手，负责把业务人员的自然语言问题翻译成 Hive SQL。

## 数据库分层
- dwd：明细层（dim_user 用户 / dim_product 商品 / dim_store 门店 / dwd_order_norm 订单 / dwd_order_item 订单明细）
- dws：汇总层（按天、周、月、品类、门店、渠道的轻度汇总）
- ads：应用层（销售日报、品类 Top10、用户价值分层、KPI 结果表）

## 硬性规则
1. 只输出一条 Hive SQL，必须是 SELECT 或 WITH 开头；禁止 INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE。
2. 所有表必须写全库名（如 dws.dws_sales_day）。
3. 销售类指标（GMV/销售额/订单量/客单价）优先查 dws 或 ads 层，它们已经只含有效订单，无需再加状态过滤。
4. 若必须查明细表 dwd.dwd_order_norm，必须加过滤条件 order_status in ('已完成','已支付') 且 pay_amount is not null。
5. 品类、门店、用户维度信息一律通过 join 维度表获取，不要臆造字段。
6. 涉及明细列表的查询加 limit 200；聚合查询不需要 limit。
7. 字段别名用中文，方便业务方直接看结果。
8. 日期字段是字符串 'yyyy-MM-dd'，比较时用字符串字面量（如 order_date between '2024-07-01' and '2024-07-31'），
   月份用 substr(order_date,1,7) = '2024-07'。
9. 拿不准字段时，选择最接近的已有字段，不要编造列名。

## 输出格式
只输出一个 ```sql 代码块，不要输出任何解释文字。
"""

FEW_SHOT = [
    {
        "q": "2024 年 7 月的 GMV 是多少？",
        "a": """```sql
select round(sum(gmv), 2) as 七月GMV
from dws.dws_sales_day
where order_date between '2024-07-01' and '2024-07-31'
```""",
    },
    {
        "q": "销售额最高的 5 个品类",
        "a": """```sql
select category as 品类, round(sum(sales), 2) as 销售额
from dws.dws_category_day
group by category
order by 销售额 desc
limit 5
```""",
    },
    {
        "q": "各省份的销售额排名",
        "a": """```sql
select province as 省份, round(sum(sales), 2) as 销售额, sum(order_cnt) as 订单量
from dws.dws_store_day
group by province
order by 销售额 desc
```""",
    },
    {
        "q": "现在复购率是多少？",
        "a": """```sql
select kpi_value as 复购率
from ads.ads_kpi_summary
where kpi_name = '复购率'
```""",
    },
    {
        "q": "去年 12 月每个渠道的销售额占比",
        "a": """```sql
select channel as 渠道,
       round(sum(sales), 2) as 销售额,
       round(sum(sales) / sum(sum(sales)) over () * 100, 2) as 占比
from dws.dws_channel_day
where substr(order_date, 1, 7) = '2024-12'
group by channel
order by 销售额 desc
```""",
    },
]


def build_user_prompt(question, schema_text, extra_hint=""):
    """把 Schema + 示例 + 问题拼成一条用户消息（单轮也能工作，不必依赖多轮记忆）"""
    parts = [
        "## 可用的表结构",
        schema_text,
        "",
        "## 示例",
    ]
    for ex in FEW_SHOT:
        parts.append(f"Q: {ex['q']}")
        parts.append(ex["a"])
        parts.append("")
    if extra_hint:
        parts.append(f"## 额外提示\n{extra_hint}\n")
    parts.append(f"## 现在的问题\nQ: {question}\nA:")
    return "\n".join(parts)


# ----------------------------------------------------------------------
# 规则兜底：没有 API Key / 网络不可用时，仍可演示"提问 -> SQL -> 结果"闭环
# 说明：这不是 NL2SQL 的主体能力，只是演示降级方案，覆盖 10 个典型问句
# ----------------------------------------------------------------------
FALLBACK_RULES = [
    (("复购率",), "select kpi_value as 复购率 from ads.ads_kpi_summary where kpi_name = '复购率'"),
    (("客单价", "aov", "AOV"), "select kpi_value as 客单价 from ads.ads_kpi_summary where kpi_name = '客单价AOV'"),
    (("活跃用户", "多少用户"), "select kpi_value as 活跃用户数 from ads.ads_kpi_summary where kpi_name = '活跃用户数'"),
    (("总gmv", "总 gmv", "全年gmv", "总销售额"), "select kpi_value as GMV from ads.ads_kpi_summary where kpi_name = 'GMV'"),
    (("品类", "category"), """select category as 品类, round(sum(sales), 2) as 销售额
from dws.dws_category_day group by category order by 销售额 desc limit 10"""),
    (("省份", "区域"), """select province as 省份, round(sum(sales), 2) as 销售额
from dws.dws_store_day group by province order by 销售额 desc"""),
    (("门店", "store"), """select store_name as 门店, round(sum(sales), 2) as 销售额
from dws.dws_store_day group by store_name order by 销售额 desc limit 10"""),
    (("渠道", "channel"), """select channel as 渠道, round(sum(sales), 2) as 销售额
from dws.dws_channel_day group by channel order by 销售额 desc"""),
    (("月度趋势", "每月", "按月"), """select month as 月份, round(gmv, 2) as GMV, order_cnt as 订单量
from dws.dws_sales_month order by month"""),
    (("用户分层", "rfm", "RFM", "价值分层"), """select segment as 客户分层, count(*) as 人数, round(sum(monetary), 2) as 累计消费
from ads.ads_user_value group by segment order by 人数 desc"""),
    (("top10", "Top10", "榜单", "排名"), "select rk as 排名, category as 品类, sales as 销售额, sales_share as 占比 from ads.ads_category_top10 order by rk"),
]


def fallback_sql(question):
    """关键词匹配生成 SQL，命中不到返回 None"""
    low = question.lower()
    for keywords, sql in FALLBACK_RULES:
        for k in keywords:
            if k.lower() in low:
                return sql
    return None
