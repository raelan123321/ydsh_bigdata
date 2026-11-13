"""
NL2SQL 正确率评测
==================
做法：对每个问题，用"人工写的标准 SQL"跑出参考结果，
     再与模型生成的 SQL 执行结果比对（单值优先比数值，多行比首行数值 + 行数）。

评测维度
  · 语法可执行率：生成的 SQL 能否在 Hive 上跑通
  · 结果一致率：与标准答案是否一致（相对误差 < 1%）
  · 平均耗时

用法
  python evaluate.py                 # 按当前配置（有 Key 走大模型，无 Key 走规则兜底）
  python evaluate.py --offline       # 强制离线
  python evaluate.py --out ../output/nl2sql_eval.md
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from nl2sql import NL2SQL, execute  # noqa: E402

# (问题, 标准 SQL, 说明)
CASES = [
    ("2024 年 7 月的 GMV 是多少",
     "select round(sum(gmv),2) as v from dws.dws_sales_day where order_date between '2024-07-01' and '2024-07-31'",
     "时间范围过滤 + 单值聚合"),
    ("全年的 GMV 是多少",
     "select kpi_value as v from ads.ads_kpi_summary where kpi_name='GMV'",
     "直接读 KPI 结果表"),
    ("客单价是多少",
     "select kpi_value as v from ads.ads_kpi_summary where kpi_name='客单价AOV'",
     "指标口径识别"),
    ("复购率是多少",
     "select kpi_value as v from ads.ads_kpi_summary where kpi_name='复购率'",
     "非聚合类 KPI（需二次计算）"),
    ("活跃用户数有多少",
     "select kpi_value as v from ads.ads_kpi_summary where kpi_name='活跃用户数'",
     "同义问法理解"),
    ("销售额最高的 5 个品类",
     "select category as k, round(sum(sales),2) as v from dws.dws_category_day group by category order by v desc limit 5",
     "分组 + 排序 + TopN"),
    ("各省份销售额排名第一的是哪个省",
     "select province as k, round(sum(sales),2) as v from dws.dws_store_day group by province order by v desc limit 1",
     "维度表关联 + 排名"),
    ("各渠道的销售额分别是多少",
     "select channel as k, round(sum(sales),2) as v from dws.dws_channel_day group by channel order by v desc",
     "多维度枚举分组"),
    ("每月的 GMV 和订单量趋势",
     "select month as k, round(gmv,2) as v, order_cnt from dws.dws_sales_month order by month",
     "时间序列输出（多列）"),
    ("重要价值客户有多少人",
     "select count(*) as v from ads.ads_user_value where segment='重要价值客户'",
     "RFM 分层表过滤"),
]


def num(x):
    try:
        return float(str(x).replace(",", "").replace("%", ""))
    except Exception:
        return None


def compare(gen_cols, gen_rows, ref_cols, ref_rows):
    """返回 (是否一致, 说明)"""
    if not gen_rows:
        return False, "生成 SQL 结果为空"
    if not ref_rows:
        return False, "标准 SQL 结果为空（数据未就绪）"

    # 单值比较
    if len(ref_rows) == 1 and len(ref_cols) == 1:
        g, r = num(gen_rows[0][0]), num(ref_rows[0][0])
        if g is None or r is None:
            return str(gen_rows[0][0]) == str(ref_rows[0][0]), "文本比较"
        if abs(r) < 1e-9:
            return abs(g) < 1e-9, f"生成 {g} / 标准 {r}"
        diff = abs(g - r) / abs(r)
        return diff < 0.01, f"生成 {g} / 标准 {r}（误差 {diff*100:.2f}%）"

    # 多行比较：首行数值 + 行数
    g_first, r_first = num(gen_rows[0][0]), num(ref_rows[0][0])
    if g_first is None or r_first is None:
        same_first = str(gen_rows[0][0]) == str(ref_rows[0][0])
    else:
        same_first = abs(g_first - r_first) <= max(1.0, abs(r_first) * 0.01)
    same_cnt = len(gen_rows) == len(ref_rows)
    detail = f"首行 {gen_rows[0][0]} vs {ref_rows[0][0]}；行数 {len(gen_rows)} vs {len(ref_rows)}"
    return (same_first and same_cnt), detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "output", "nl2sql_eval.md"))
    a = ap.parse_args()

    engine = NL2SQL(offline=a.offline)
    print(f"运行模式：{engine.mode} | Schema 来源：{engine.schema_source}\n")

    rows = []
    ok_exec = ok_match = 0
    for i, (q, ref_sql, tag) in enumerate(CASES, 1):
        r = engine.ask(q, do_exec=True)
        exec_ok = r["sql"] is not None and r["error"] is None
        match, detail = False, r["error"] or "未执行"
        if exec_ok:
            try:
                rc, rr = execute(ref_sql)
                match, detail = compare(r["columns"], r["rows"], rc, rr)
            except Exception as e:
                detail = f"标准 SQL 执行失败：{e}"
        ok_exec += int(exec_ok)
        ok_match += int(match)
        rows.append({
            "no": i, "question": q, "tag": tag,
            "sql": r["sql"], "exec_ok": exec_ok, "match": match,
            "detail": detail, "elapsed": r["elapsed"], "error": r["error"],
        })
        print(f"[{i:02d}] {'OK ' if exec_ok else 'ERR'} {'一致' if match else '不一致'} | {q} | {detail}")

    n = len(CASES)
    rate_exec, rate_match = ok_exec / n * 100, ok_match / n * 100
    avg_t = sum(x["elapsed"] for x in rows) / n

    md = [
        "# NL2SQL 评测结果", "",
        f"- 运行模式：`{engine.mode}`",
        f"- Schema 来源：`{engine.schema_source}`",
        f"- 用例数：{n}",
        f"- **可执行率：{ok_exec}/{n} = {rate_exec:.0f}%**",
        f"- **结果一致率：{ok_match}/{n} = {rate_match:.0f}%**",
        f"- 平均耗时：{avg_t:.2f}s", "",
        "| # | 问题 | 考察点 | SQL 可执行 | 结果一致 | 比对说明 |",
        "|---|---|---|---|---|---|",
    ]
    for x in rows:
        md.append(f"| {x['no']} | {x['question']} | {x['tag']} | {'✅' if x['exec_ok'] else '❌'} | "
                  f"{'✅' if x['match'] else '❌'} | {x['detail']} |")
    md += ["", "## 生成的 SQL 明细", ""]
    for x in rows:
        md.append(f"### {x['no']}. {x['question']}")
        md.append("```sql")
        md.append((x["sql"] or x["error"] or "").strip())
        md.append("```")
        md.append("")

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    with open(os.path.splitext(a.out)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump({"mode": engine.mode, "schema_source": engine.schema_source,
                   "exec_rate": rate_exec, "match_rate": rate_match, "cases": rows},
                  f, ensure_ascii=False, indent=2)

    print(f"\n可执行率 {rate_exec:.0f}% | 一致率 {rate_match:.0f}% | 平均耗时 {avg_t:.2f}s")
    print(f"报告已写入 {os.path.abspath(a.out)}")


if __name__ == "__main__":
    main()
