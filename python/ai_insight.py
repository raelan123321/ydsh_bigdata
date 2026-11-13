"""
AI 智能洞察：异常检测 + 归因 + 自动报告
========================================
三步走
  1. 检测：日 GMV 的 z-score 异常、周环比骤降、品类结构突变
  2. 归因：把"某天 GMV 相对基准的偏差"按渠道/品类拆解，量化各维度贡献度
  3. 成文：规则模板生成结构化报告；若配置了 LLM，再让模型写一段业务解读（可选）

用法
  python ai_insight.py                      # 从 Hive 读取
  python ai_insight.py --source csv --csvdir ../output/insight/data
  python ai_insight.py --no-llm             # 只用规则模板成文
"""

import argparse
import json
import os
import sys
from datetime import datetime

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "nl2sql"))

# 异常判定阈值（写在代码里，便于答辩时说明"为什么是这个数"）
Z_THRESHOLD = 2.0          # 日 GMV 偏离均值超过 2 个标准差
WOW_DROP_THRESHOLD = 30.0  # 周环比跌幅超过 30%
SHIFT_THRESHOLD = 5.0      # 品类占比变动超过 5 个百分点


def hive_query(sql):
    from pyhive import hive
    conn = hive.Connection(
        host=os.environ.get("HIVE_HOST", "localhost"),
        port=int(os.environ.get("HIVE_PORT", 10000)),
        username=os.environ.get("HIVE_USER", "hive"), database="dws")
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0].split(".")[-1] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def load_all(source="hive", csvdir=None):
    queries = {
        "daily": "select order_date, gmv, order_cnt, aov, user_cnt from dws.dws_sales_day order by order_date",
        "month": "select month, gmv, order_cnt, aov, user_cnt from dws.dws_sales_month order by month",
        "category": "select order_date, category, sales, qty, order_cnt from dws.dws_category_day",
        "channel": "select order_date, channel, sales, order_cnt from dws.dws_channel_day",
        "segment": "select segment, count(*) as user_cnt, sum(monetary) as amount from ads.ads_user_value group by segment",
    }
    data = {}
    if source == "csv":
        import csv
        for k in queries:
            p = os.path.join(csvdir, f"{k}.csv")
            if not os.path.exists(p):
                print(f"[WARN] 缺少 {p}，该维度跳过")
                data[k] = []
                continue
            with open(p, encoding="utf-8-sig") as f:
                data[k] = list(csv.DictReader(f))
    else:
        for k, q in queries.items():
            data[k] = hive_query(q)
    return data


def to_float(rows, keys):
    for r in rows:
        for k in keys:
            if k in r:
                try:
                    r[k] = float(r[k])
                except (TypeError, ValueError):
                    r[k] = 0.0
    return rows


# ----------------------------------------------------------------------
# 1) 异常检测
# ----------------------------------------------------------------------
def detect_daily_anomalies(daily):
    gmv = np.array([float(r["gmv"]) for r in daily], dtype=float)
    mu, sd = gmv.mean(), gmv.std(ddof=0)
    anomalies = []
    for i, r in enumerate(daily):
        z = (gmv[i] - mu) / sd if sd > 0 else 0
        if abs(z) >= Z_THRESHOLD:
            anomalies.append({
                "type": "日 GMV 异常",
                "date": r["order_date"],
                "value": round(gmv[i], 2),
                "baseline": round(float(mu), 2),
                "z": round(float(z), 2),
                "desc": f"{r['order_date']} GMV {gmv[i]:,.0f} 元，偏离日均 {mu:,.0f} 元 {z:+.1f} 个标准差",
            })
    return anomalies, {"mean": float(mu), "std": float(sd)}


def detect_week_drop(daily):
    """按周聚合，找环比跌幅超阈值的周（只比较完整周：7 天都有数据，避免跨年残周误判）"""
    weeks = {}
    for r in daily:
        d = r["order_date"]
        y, m, day = map(int, d.split("-"))
        iso = datetime(y, m, day).isocalendar()
        wk = f"{iso.year}-W{iso.week:02d}"
        weeks.setdefault(wk, {"gmv": 0.0, "cnt": 0, "days": 0})
        weeks[wk]["gmv"] += float(r["gmv"])
        weeks[wk]["cnt"] += int(r["order_cnt"])
        weeks[wk]["days"] += 1
    keys = [k for k in sorted(weeks) if weeks[k]["days"] >= 7]
    out = []
    for prev, cur in zip(keys, keys[1:]):
        a, b = weeks[prev]["gmv"], weeks[cur]["gmv"]
        if a > 0:
            chg = (b - a) / a * 100
            if chg <= -WOW_DROP_THRESHOLD:
                out.append({
                    "type": "周环比骤降", "week": cur, "prev_week": prev,
                    "value": round(b, 2), "baseline": round(a, 2), "change_pct": round(chg, 2),
                    "desc": f"{cur} 周 GMV {b:,.0f} 元，较 {prev} 周 {a:,.0f} 元下降 {abs(chg):.1f}%",
                })
    return out


def detect_category_shift(category):
    """年度后半段 vs 前半段品类占比变化"""
    dates = sorted({r["order_date"] for r in category})
    if not dates:
        return [], {}
    mid = dates[len(dates) // 2]
    agg = {}
    for r in category:
        k = r["category"]
        half = "H1" if r["order_date"] < mid else "H2"
        agg.setdefault(k, {"H1": 0.0, "H2": 0.0})[half] += float(r["sales"])
    t1, t2 = sum(v["H1"] for v in agg.values()), sum(v["H2"] for v in agg.values())
    out = []
    for k, v in agg.items():
        s1 = v["H1"] / t1 * 100 if t1 else 0
        s2 = v["H2"] / t2 * 100 if t2 else 0
        if abs(s2 - s1) >= SHIFT_THRESHOLD:
            out.append({
                "type": "品类结构突变", "category": k,
                "change_pp": round(s2 - s1, 2),
                "desc": f"{k} 销售额占比由 {s1:.1f}% 变为 {s2:.1f}%（{s2-s1:+.1f} 个百分点）",
            })
    return out, {"split_date": mid, "h1_total": round(t1, 2), "h2_total": round(t2, 2)}


# ----------------------------------------------------------------------
# 2) 归因：把偏差拆到渠道 / 品类
# ----------------------------------------------------------------------
def attribute_channel(channel, target_date, baseline_start, baseline_end):
    """目标日 vs 基准区间（通常前 7 天）各渠道销售额差额，量化贡献"""
    tgt, base = {}, {}
    for r in channel:
        sales = float(r["sales"])
        if r["order_date"] == target_date:
            tgt[r["channel"]] = tgt.get(r["channel"], 0.0) + sales
        if baseline_start <= r["order_date"] <= baseline_end:
            base.setdefault(r["channel"], []).append(sales)
    rows = []
    for ch in set(list(tgt) + list(base)):
        b = sum(base.get(ch, [0.0])) / max(1, len(set(r["order_date"] for r in channel if baseline_start <= r["order_date"] <= baseline_end)))
        t = tgt.get(ch, 0.0)
        rows.append({"channel": ch, "target": round(t, 2), "baseline": round(b, 2),
                     "diff": round(t - b, 2)})
    total_diff = sum(r["diff"] for r in rows)
    for r in rows:
        r["contribution_pct"] = round(r["diff"] / total_diff * 100, 1) if total_diff else 0.0
    return sorted(rows, key=lambda x: -abs(x["diff"]))


def attribute_category(category, target_date, baseline_start, baseline_end, ndays=7):
    tgt, base = {}, {}
    for r in category:
        s = float(r["sales"])
        if r["order_date"] == target_date:
            tgt[r["category"]] = tgt.get(r["category"], 0.0) + s
        elif baseline_start <= r["order_date"] <= baseline_end:
            base[r["category"]] = base.get(r["category"], 0.0) + s
    rows = []
    for c in set(list(tgt) + list(base)):
        b = base.get(c, 0.0) / max(1, ndays)
        t = tgt.get(c, 0.0)
        rows.append({"category": c, "target": round(t, 2), "baseline": round(b, 2), "diff": round(t - b, 2)})
    total = sum(r["diff"] for r in rows)
    for r in rows:
        r["contribution_pct"] = round(r["diff"] / total * 100, 1) if total else 0.0
    return sorted(rows, key=lambda x: -abs(x["diff"]))


# ----------------------------------------------------------------------
# 3) 成文
# ----------------------------------------------------------------------
def consistency_check(daily, category):
    """口径一致性校验：明细金额合计 vs 订单实付合计
    为什么要查：品类分析的金额来自 dwd_order_item（数量*单价*折扣），
    与订单实付 pay_amount 是两条独立链路，若不勾稽，品类销售额只能用于"结构对比"，
    不能与 GMV 直接加总或换算占比。
    """
    gmv_total = sum(float(r["gmv"]) for r in daily)
    item_total = sum(float(r["sales"]) for r in category) if category else 0.0
    ratio = item_total / gmv_total if gmv_total else 0.0
    return {
        "gmv_total": round(gmv_total, 2),
        "item_total": round(item_total, 2),
        "ratio": round(ratio, 2),
        "aligned": 0.9 <= ratio <= 1.1,
    }


def build_report(data, anomalies, stats, week_drops, cat_shifts, cat_meta, attrib, consistency=None):
    daily = data["daily"]
    total_gmv = sum(float(r["gmv"]) for r in daily)
    total_cnt = sum(int(r["order_cnt"]) for r in daily)
    dates = [r["order_date"] for r in daily]

    lines = []
    lines.append("# 经营数据智能洞察报告")
    lines.append("")
    lines.append(f"> 自动生成时间：{datetime.now():%Y-%m-%d %H:%M}　|　数据范围：{dates[0]} ~ {dates[-1]}　|　样本 {len(daily)} 天")
    lines.append("")
    lines.append("## 一、核心指标概览")
    lines.append("")
    lines.append(f"- 累计 GMV：**{total_gmv:,.2f} 元**，日均 **{total_gmv/len(daily):,.2f} 元**")
    lines.append(f"- 累计订单量：**{total_cnt:,} 单**，日均 {total_cnt/len(daily):.0f} 单")
    lines.append(f"- 日均客单价：**{total_gmv/total_cnt:,.2f} 元**")
    lines.append(f"- 日 GMV 标准差 {stats['std']:,.2f} 元，波动系数（CV）{stats['std']/stats['mean']*100:.1f}%")
    lines.append(f"- 日下单用户数区间 {min(int(r['user_cnt']) for r in daily)} ~ {max(int(r['user_cnt']) for r in daily)} 人/日")
    if consistency:
        flag = "✅ 勾稽一致" if consistency["aligned"] else "⚠️ 不勾稽"
        lines.append(f"- 口径一致性校验：明细金额合计 {consistency['item_total']:,.2f} 元 vs 订单实付合计 "
                     f"{consistency['gmv_total']:,.2f} 元，比值 **{consistency['ratio']}×** —— {flag}")
        if not consistency["aligned"]:
            lines.append("  - 含义：`dwd_order_item` 的 `quantity*unit_price*(1-discount)` 与订单表 `pay_amount` 是两条独立生成链路，"
                         "两者不可加总。**品类/商品类金额指标只能做结构占比与趋势对比，不能与 GMV 换算**；"
                         "若需口径统一，应在上游补一条「订单金额 = 明细金额之和」的勾稽校验规则。")
    lines.append("")

    lines.append("## 二、异常检测结果")
    lines.append("")
    if not anomalies and not week_drops and not cat_shifts:
        lines.append("未检出超过阈值的异常。")
    else:
        lines.append(f"判定阈值：日 GMV |z| ≥ {Z_THRESHOLD}；周环比跌幅 ≥ {WOW_DROP_THRESHOLD}%；品类占比变动 ≥ {SHIFT_THRESHOLD} 个百分点。")
        lines.append("")
        lines.append("| 类型 | 对象 | 指标值 | 基准值 | 偏离 |")
        lines.append("|---|---|---|---|---|")
        for a in anomalies[:10]:
            lines.append(f"| 日 GMV 异常 | {a['date']} | {a['value']:,.0f} | {a['baseline']:,.0f} | z={a['z']:+.1f} |")
        for w in week_drops[:10]:
            lines.append(f"| 周环比骤降 | {w['week']} | {w['value']:,.0f} | {w['baseline']:,.0f} | {w['change_pct']:+.1f}% |")
        for c in cat_shifts[:10]:
            lines.append(f"| 品类结构突变 | {c['category']} | — | — | {c['change_pp']:+.1f}pp |")
    lines.append("")

    lines.append("## 三、归因分析")
    lines.append("")
    if attrib and attrib.get("target_date"):
        a = attrib
        lines.append(f"**目标日 {a['target_date']}，基准为前 7 天日均。**")
        lines.append("")
        lines.append(f"- 当日 GMV {a['day_gmv']:,.2f} 元，较基准 {a['baseline_gmv']:,.2f} 元，偏差 **{a['diff']:+,.2f} 元（{a['diff_pct']:+.1f}%）**")
        lines.append("")
        lines.append("### 渠道贡献拆解")
        lines.append("")
        lines.append("| 渠道 | 当日销售额 | 基准日均 | 差额 | 贡献占比 |")
        lines.append("|---|---|---|---|---|")
        for r in a["channel"][:6]:
            lines.append(f"| {r['channel']} | {r['target']:,.0f} | {r['baseline']:,.0f} | {r['diff']:+,.0f} | {r['contribution_pct']:+.1f}% |")
        lines.append("")
        lines.append("### 品类贡献拆解")
        lines.append("")
        lines.append("> 口径提示：本表金额来自订单明细（数量×单价×折扣），与订单实付口径不同，**只看贡献结构，不与上方 GMV 绝对值对比**。")
        lines.append("")
        lines.append("| 品类 | 当日销售额 | 基准日均 | 差额 | 贡献占比 |")
        lines.append("|---|---|---|---|---|")
        for r in a["category"][:6]:
            lines.append(f"| {r['category']} | {r['target']:,.0f} | {r['baseline']:,.0f} | {r['diff']:+,.0f} | {r['contribution_pct']:+.1f}% |")
        lines.append("")
        top_ch = a["channel"][0] if a["channel"] else None
        top_cat = a["category"][0] if a["category"] else None
        if top_ch:
            lines.append(f"**结论**：当日波动主要由「{top_ch['channel']}」渠道解释（贡献 {top_ch['contribution_pct']:+.1f}%，差额 {top_ch['diff']:+,.0f} 元）"
                         + (f"，品类侧主要是「{top_cat['category']}」（{top_cat['contribution_pct']:+.1f}%）。" if top_cat else "。"))
        lines.append("")
    else:
        lines.append("（无足够数据完成归因）")
        lines.append("")

    lines.append("## 四、业务建议")
    lines.append("")
    tips = []
    if cat_shifts:
        c = max(cat_shifts, key=lambda x: abs(x["change_pp"]))
        tips.append(f"「{c['category']}」品类占比变动 {c['change_pp']:+.1f}pp，建议复核该类目的选品与定价策略，确认是策略使然还是供给（库存/上架）异常。")
    if week_drops:
        w = week_drops[0]
        tips.append(f"{w['week']} 周 GMV 环比下滑 {abs(w['change_pct']):.1f}%，建议优先排查该周的渠道投放与门店营业状态。")
    tips.append(f"日均 GMV 波动系数 {stats['std']/stats['mean']*100:.1f}%，"
                + ("波动较平稳，可按日均水平做库存与排班规划。" if stats["std"]/stats["mean"] < 0.5
                   else "波动偏高，建议按周内周期（周末/工作日）分档制定目标，而非用统一日均。"))
    tips.append("客单价与订单量的贡献需分开看：GMV 下滑若由订单量驱动应抓流量，若由客单价驱动应抓连带销售与满减门槛设置。")
    for i, t in enumerate(tips, 1):
        lines.append(f"{i}. {t}")
    lines.append("")
    lines.append("---")
    lines.append("*本报告由 ai_insight.py 自动生成：异常检测用统计阈值，归因用差额贡献度拆解，结论段可用大模型润色。*")
    return "\n".join(lines)


def llm_polish(report_md):
    """可选：让大模型写一段业务解读，追加到报告末尾"""
    try:
        from nl2sql import LLMClient
        c = LLMClient()
        if not c.available:
            return None
        prompt = ("下面是一份零售经营数据洞察报告，请以数据分析师口吻写 200 字以内的「管理层摘要」，"
                  "只讲最值得关注的 2 个问题和 2 条建议，不要重复罗列数字：\n\n" + report_md[:6000])
        return c.complete("你是资深零售数据分析师，输出简洁、直接、可执行。", prompt)
    except Exception as e:
        return f"（大模型解读生成失败：{e}）"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["hive", "csv"], default="hive")
    ap.add_argument("--csvdir", default=os.path.join(HERE, "..", "output", "insight", "data"))
    ap.add_argument("--outdir", default=os.path.join(HERE, "..", "output", "insight"))
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(HERE, "nl2sql", ".env"))
    except ImportError:
        pass

    data = load_all(a.source, a.csvdir)
    for k, keys in (("daily", ["gmv", "aov", "user_cnt"]), ("month", ["gmv", "aov", "user_cnt"]),
                    ("category", ["sales", "qty"]), ("channel", ["sales"]), ("segment", ["user_cnt", "amount"])):
        data[k] = to_float(data[k], keys)

    daily = data["daily"]
    anomalies, stats = detect_daily_anomalies(daily)
    week_drops = detect_week_drop(daily)
    cat_shifts, cat_meta = detect_category_shift(data["category"])

    # 选"偏差最大的一天"做归因
    attrib = None
    if anomalies:
        worst = max(anomalies, key=lambda x: abs(x["z"]))
        target = worst["date"]
        idx = [r["order_date"] for r in daily].index(target)
        if idx >= 7:
            base_dates = [r["order_date"] for r in daily[idx - 7:idx]]
            day_gmv = float(daily[idx]["gmv"])
            base_gmv = sum(float(daily[j]["gmv"]) for j in range(idx - 7, idx)) / 7
            attrib = {
                "target_date": target,
                "day_gmv": round(day_gmv, 2),
                "baseline_gmv": round(base_gmv, 2),
                "diff": round(day_gmv - base_gmv, 2),
                "diff_pct": round((day_gmv - base_gmv) / base_gmv * 100, 2) if base_gmv else 0,
                "channel": attribute_channel(data["channel"], target, base_dates[0], base_dates[-1]),
                "category": attribute_category(data["category"], target, base_dates[0], base_dates[-1]),
            }

    consistency = consistency_check(daily, data["category"])
    report = build_report(data, anomalies, stats, week_drops, cat_shifts, cat_meta, attrib, consistency)
    if not a.no_llm:
        summary = llm_polish(report)
        if summary:
            report += "\n\n## 五、管理层摘要（大模型生成）\n\n" + summary.strip() + "\n"

    os.makedirs(a.outdir, exist_ok=True)
    out_md = os.path.join(a.outdir, "AI洞察报告.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(report)
    with open(os.path.join(a.outdir, "insight.json"), "w", encoding="utf-8") as f:
        json.dump({"anomalies": anomalies, "week_drops": week_drops, "category_shifts": cat_shifts,
                   "stats": stats, "attribution": attrib}, f, ensure_ascii=False, indent=2)

    print(f"异常 {len(anomalies)} 条 | 周环比骤降 {len(week_drops)} 条 | 品类突变 {len(cat_shifts)} 条")
    print(f"报告已写入 {os.path.abspath(out_md)}")


if __name__ == "__main__":
    main()
