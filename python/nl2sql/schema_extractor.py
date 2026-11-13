"""
Schema 抽取：把 Hive 元数据转成可注入 Prompt 的紧凑文本
=========================================================
为什么需要这一步
  · 大模型不知道我们的表结构，必须把"库表列 + 业务口径"喂给它
  · 全量元数据太长会挤爆上下文且降低准确率，因此只抽 4 个相关库、
    并按"每表一行 + 列清单"的紧凑格式压缩
  · 抽取结果缓存成 schema_cache.json，NL2SQL 每次启动直接复用（元数据变更时 --refresh）

用法
  python schema_extractor.py            # 抽取并打印
  python schema_extractor.py --refresh  # 忽略缓存重新抽取
"""

import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "schema_cache.json")

# 参与 NL2SQL 的库表白名单（不把 ODS 原始层暴露给模型，避免它去查脏数据）
TABLES = {
    "dwd": ["dim_user", "dim_product", "dim_store", "dwd_order_norm", "dwd_order_item"],
    "dws": ["dws_sales_day", "dws_sales_week", "dws_sales_month",
            "dws_category_day", "dws_store_day", "dws_channel_day"],
    "ads": ["ads_sales_daily", "ads_category_top10", "ads_user_value",
            "ads_kpi_summary", "ads_kpi_month"],
}

# 业务口径说明：这部分是"模型不可能自己知道"的知识，必须显式写入 Prompt
BUSINESS_RULES = {
    "dwd.dwd_order_norm": "订单事实表(已标准化)。有效订单 = order_status in ('已完成','已支付') 且 pay_amount is not null；"
                          "已取消/待支付/退款中/其他 不计入销售指标",
    "dwd.dwd_order_item": "订单明细(已清洗数量与单价)，item_amount = quantity*unit_price*(1-discount)，已冗余 order_date",
    "dws.dws_sales_day": "按天汇总，已只含有效订单，直接查它算 GMV/订单量/客单价最省事",
    "ads.ads_kpi_summary": "5 项核心 KPI 结果表(GMV/订单量/客单价AOV/活跃用户数/复购率)",
    "ads.ads_user_value": "用户 RFM 分层结果，segment 取值：重要价值客户/重要保持客户/重要发展客户/一般价值客户/一般保持客户/流失预警客户/新客",
    "ads.ads_category_top10": "品类销售 Top10，sales_share/cum_share 为占比与累计占比(%)",
}

# 离线兜底（Hive 不可达时仍可生成 Prompt，保证演示环境无关）
SCHEMA_FALLBACK = {
    "dwd.dim_user": "user_id string, user_name string, gender string, age int, city string, province string, member_level string",
    "dwd.dim_product": "product_id string, product_name string, category string, sub_category string, brand string, price double",
    "dwd.dim_store": "store_id string, store_name string, province string, city string, district string, address string, open_date string, area int, manager string",
    "dwd.dwd_order_norm": "order_id string, user_id string, store_id string, order_timestamp string, pay_amount double, discount_amount double, raw_status string, order_status string, raw_channel string, channel string, order_date string",
    "dwd.dwd_order_item": "item_id string, order_id string, product_id string, quantity int, unit_price double, discount double, item_amount double, order_date string",
    "dws.dws_sales_day": "order_date string, order_cnt bigint, gmv double, aov double, user_cnt bigint, avg_discount double",
    "dws.dws_sales_week": "week_start string, year_week string, order_cnt bigint, gmv double, user_cnt bigint",
    "dws.dws_sales_month": "month string, order_cnt bigint, gmv double, aov double, user_cnt bigint",
    "dws.dws_category_day": "order_date string, category string, sales double, qty bigint, order_cnt bigint",
    "dws.dws_store_day": "order_date string, store_id string, store_name string, province string, city string, sales double, order_cnt bigint, user_cnt bigint",
    "dws.dws_channel_day": "order_date string, channel string, sales double, order_cnt bigint, user_cnt bigint",
    "ads.ads_sales_daily": "order_date string, gmv double, order_cnt bigint, aov double, user_cnt bigint, dod_rate double, gmv_ma7 double",
    "ads.ads_category_top10": "rk int, category string, sales double, qty bigint, order_cnt bigint, sales_share double, cum_share double",
    "ads.ads_user_value": "user_id string, last_order_date string, recency_days int, frequency bigint, monetary double, r_score int, f_score int, m_score int, rfm_score int, segment string",
    "ads.ads_kpi_summary": "kpi_name string, kpi_value double, kpi_unit string, calc_desc string, stat_scope string, calc_time string",
    "ads.ads_kpi_month": "month string, gmv double, order_cnt bigint, aov double, user_cnt bigint, repurchase_rate double",
}


def extract_from_hive(host="localhost", port=10000, user="hive"):
    from pyhive import hive

    conn = hive.Connection(host=host, port=port, username=user)
    schema = {}
    try:
        cur = conn.cursor()
        for db, tables in TABLES.items():
            for t in tables:
                full = f"{db}.{t}"
                try:
                    cur.execute(f"desc {full}")
                    cols = []
                    for row in cur.fetchall():
                        name, dtype = row[0], row[1]
                        if not name or name.startswith("#") or dtype is None:
                            break  # desc 输出的分区信息段之后不再有列
                        comment = row[2] if len(row) > 2 and row[2] else ""
                        cols.append(f"{name} {dtype}" + (f" -- {comment}" if comment else ""))
                    if cols:
                        schema[full] = ", ".join(cols)
                except Exception as e:
                    print(f"[WARN] {full} 抽取失败: {e}")
    finally:
        conn.close()
    return schema


def load_schema(refresh=False, host="localhost", port=10000):
    if not refresh and os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("schema"):
            return data["schema"], data.get("source", "cache")

    try:
        schema = extract_from_hive(host=host, port=port)
        source = "hive"
    except Exception as e:
        print(f"[WARN] Hive 元数据不可达（{e}），使用内置 Schema 快照")
        schema, source = {}, "fallback"

    if not schema:
        schema, source = SCHEMA_FALLBACK, "fallback"

    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump({"source": source, "schema": schema}, f, ensure_ascii=False, indent=2)
    return schema, source


def build_schema_text(schema, max_cols=40):
    """压缩成 Prompt 可读的文本：表名 + 列清单 + 业务口径"""
    lines = []
    for full in sorted(schema.keys()):
        cols = schema[full]
        if cols.count(",") > max_cols:
            cols = ", ".join(cols.split(", ")[:max_cols]) + " ..."
        lines.append(f"- {full}({cols})")
        if full in BUSINESS_RULES:
            lines.append(f"    口径: {BUSINESS_RULES[full]}")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--host", default=os.environ.get("HIVE_HOST", "localhost"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("HIVE_PORT", 10000)))
    a = ap.parse_args()
    s, src = load_schema(refresh=a.refresh, host=a.host, port=a.port)
    print(f"# 来源: {src} | 表数: {len(s)}\n")
    print(build_schema_text(s))
