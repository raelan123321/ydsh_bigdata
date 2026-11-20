# -*- coding: utf-8 -*-
"""生成大屏数据 JSON（仅标准库，无第三方依赖）
数据源：交付数据/*.csv（KPI 结果）+ E:/模拟数据（时段×品类热力图）
"""
import csv
import json
import os

D = r"C:/Users/16851/WorkBuddy/2026-11-02-08-30-31/交付数据"
E = r"E:/模拟数据"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)


def read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def dump(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    print("wrote", name)


# 1) KPI 摘要卡片
dump("kpi.json", [
    {"name": r["kpi_name"], "value": float(r["kpi_value"]), "unit": r["kpi_unit"]}
    for r in read_csv(os.path.join(D, "kpi_summary.csv"))
])

# 2) 月度趋势（折线/散点）
m = read_csv(os.path.join(D, "kpi_month.csv"))
dump("month_trend.json", {
    "months": [r["month"] for r in m],
    "gmv": [round(float(r["gmv"]), 2) for r in m],
    "order_cnt": [int(float(r["order_cnt"])) for r in m],
    "aov": [round(float(r["aov"]), 2) for r in m],
})

# 3) 品类 Top10（柱状）
c = read_csv(os.path.join(D, "category_top10.csv"))
dump("category.json", {
    "categories": [r["category"] for r in c],
    "sales": [round(float(r["sales"]), 2) for r in c],
    "qty": [int(float(r["qty"])) for r in c],
})

# 4) 渠道占比（饼图）
dump("channel.json", [
    {"name": r["channel"], "value": round(float(r["sales"]), 2)}
    for r in read_csv(os.path.join(D, "channel_sales.csv"))
])

# 5) 区域分布（地图）
dump("region.json", [
    {"name": r["province"], "value": round(float(r["sales"]), 2), "cnt": int(float(r["cnt"]))}
    for r in read_csv(os.path.join(D, "region_sales.csv"))
])

# 6) 时段×品类热力图：订单时间 join 明细品类
def read_col(path):
    with open(path, encoding="utf-8-sig") as f:
        return {r["order_id"]: r for r in csv.DictReader(f)}

orders = {r["order_id"]: r for r in csv.DictReader(open(os.path.join(E, "ods_order.csv"), encoding="utf-8-sig"))}
products = {r["product_id"]: r["category"] for r in csv.DictReader(open(os.path.join(E, "ods_product.csv"), encoding="utf-8-sig"))}

heat = {}  # (hour, category) -> amount
with open(os.path.join(E, "ods_order_item.csv"), encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        o = orders.get(row["order_id"])
        cat = products.get(row["product_id"])
        if not o or not cat:
            continue
        hour = int(o["order_time"].split(":")[0])
        amt = float(row["unit_price"]) * float(row["quantity"]) * (1 - float(row["discount"]))
        key = (hour, cat)
        heat[key] = heat.get(key, 0.0) + amt

hours = sorted({k[0] for k in heat})
cats = sorted({k[1] for k in heat})
dump("heatmap.json", {
    "hours": [f"{h:02d}:00" for h in hours],
    "categories": cats,
    "data": [[cats.index(cat), hours.index(h), round(heat[(h, cat)], 1)]
             for (h, cat) in sorted(heat)],
})

# 7) 散点：月度 GMV vs 订单量（相关性）
dump("scatter.json", [
    {"month": r["month"], "gmv": round(float(r["gmv"]), 2), "order_cnt": int(float(r["order_cnt"])),
     "aov": round(float(r["aov"]), 2)}
    for r in m
])

print("ALL DONE")
