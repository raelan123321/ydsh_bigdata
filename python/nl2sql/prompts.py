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
7. 字段别名用英文小写（如 gmv、sales、order_cnt）。Hive 3.1 对未加反引号的中文别名会直接解析失败，确需中文别名时必须用反引号包裹（如 `销售额`）。
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
select round(sum(gmv), 2) as gmv_july
from dws.dws_sales_day
where order_date between '2024-07-01' and '2024-07-31'
```""",
    },
    {
        "q": "销售额最高的 5 个品类",
        "a": """```sql
select category, round(sum(sales), 2) as sales
from dws.dws_category_day
group by category
order by sales desc
limit 5
```""",
    },
    {
        "q": "各省份的销售额排名",
        "a": """```sql
select province, round(sum(sales), 2) as sales, sum(order_cnt) as order_cnt
from dws.dws_store_day
group by province
order by sales desc
```""",
    },
    {
        "q": "现在复购率是多少？",
        "a": """```sql
select kpi_value as repurchase_rate
from ads.ads_kpi_summary
where kpi_name = '复购率'
```""",
    },
    {
        "q": "去年 12 月每个渠道的销售额占比",
        "a": """```sql
select channel,
       round(sum(sales), 2) as sales,
       round(sum(sales) / sum(sum(sales)) over () * 100, 2) as share_pct
from dws.dws_channel_day
where substr(order_date, 1, 7) = '2024-12'
group by channel
order by sales desc
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
import re  # noqa: E402  （仅兜底规则使用）


def _month_range(q):
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", q)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{4})-(\d{2})", q)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


def _topn(q, default=10):
    m = re.search(r"(\d+)\s*(?:个|名|条)", q)
    if not m:
        m = re.search(r"[Tt]op\s*(\d+)", q)
    return int(m.group(1)) if m else default


def fallback_sql(question):
    """关键词 + 正则兜底：覆盖常见问句形态。
    注意：所有别名使用英文小写——Hive 3.1 对未加反引号的中文别名会解析失败，
    这条约束也是 Prompt 里必须写明的规则（实测踩坑）。
    """
    q = question.strip()
    low = q.lower()
    is_gmv = ("gmv" in low or "销售额" in q or "成交额" in q or "营业额" in q)

    # 指定月份
    month = _month_range(q)
    if month and is_gmv:
        return (f"select round(sum(gmv), 2) as gmv from dws.dws_sales_day "
                f"where substr(order_date, 1, 7) = '{month}'")

    if "复购" in q:
        # 月度口径：当月有效订单≥2次的用户 / 当月下单用户（dwd 实时计算）
        if "月" in q or month:
            where_m = f" and substr(order_date, 1, 7) = '{month}'" if month else ""
            return (
                "select m as month_id, "
                "count(distinct user_id) as act_users, "
                "count(distinct case when mcnt >= 2 then user_id end) as repeat_users, "
                "round(count(distinct case when mcnt >= 2 then user_id end) "
                "/ count(distinct user_id) * 100, 2) as repurchase_rate "
                "from (select user_id, substr(order_date, 1, 7) as m, count(*) as mcnt "
                "from dwd.dwd_order_norm "
                "where order_status in ('已完成', '已支付')" + where_m + " "
                "group by user_id, substr(order_date, 1, 7)) t "
                "group by m order by m"
            )
        # 全年口径：全年人均约 9.2 单，几乎所有用户复购，故为 100%
        return "select kpi_value as repurchase_rate from ads.ads_kpi_summary where kpi_name = '复购率'"
    if "客单价" in q or "aov" in low:
        return "select kpi_value as aov from ads.ads_kpi_summary where kpi_name = '客单价AOV'"
    if "活跃用户" in q or "多少用户" in q:
        return "select kpi_value as active_users from ads.ads_kpi_summary where kpi_name = '活跃用户数'"
    if ("全年" in q or "总" in q or "整体" in q) and is_gmv:
        return "select kpi_value as gmv from ads.ads_kpi_summary where kpi_name = 'GMV'"

    if "重要价值" in q or "分层" in q or "rfm" in low:
        if "重要价值" in q:
            return "select count(*) as user_cnt from ads.ads_user_value where segment = '重要价值客户'"
        return ("select segment, count(*) as user_cnt, round(sum(monetary), 2) as amount "
                "from ads.ads_user_value group by segment order by user_cnt desc")

    if "品类" in q or "category" in low:
        n = _topn(q, 10)
        return (f"select category, round(sum(sales), 2) as sales from dws.dws_category_day "
                f"group by category order by sales desc limit {n}")
    if "省份" in q or "省" in q or "区域" in q:
        n = 1 if ("第一" in q or "最高" in q or "最大" in q) else 200
        return (f"select province, round(sum(sales), 2) as sales from dws.dws_store_day "
                f"group by province order by sales desc limit {n}")
    if "门店" in q or "store" in low:
        n = _topn(q, 10)
        return (f"select store_name, round(sum(sales), 2) as sales from dws.dws_store_day "
                f"group by store_name order by sales desc limit {n}")
    if "渠道" in q or "channel" in low:
        return ("select channel, round(sum(sales), 2) as sales from dws.dws_channel_day "
                "group by channel order by sales desc")
    if "月" in q and ("趋势" in q or "每月" in q or "按月" in q):
        return ("select month, round(gmv, 2) as gmv, order_cnt from dws.dws_sales_month "
                "order by month")
    if "榜单" in q or "排名" in q or "top" in low:
        return ("select rk, category, sales, sales_share from ads.ads_category_top10 order by rk")
    return None
