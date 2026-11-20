# -*- coding: utf-8 -*-
"""第 4 周压力测试脚本（子任务 5）
两部分：
  1. Hive 查询压测：带分区裁剪 vs 全表扫描，多轮并发，记录响应时间分布
  2. 大屏 API HTTP 压测：并发请求 /api/all，记录吞吐与延迟分布

用法：
  python press_test.py --hive            # Hive 查询对比（需可连 Hive）
  python press_test.py --http            # 大屏 API 压测（需 screen-api 已启动）
  python press_test.py --all             # 两者都跑
结果输出 JSON 到 output/week4/press_result.json，并打印摘要表。
"""
import argparse
import concurrent.futures as cf
import json
import os
import statistics
import time

OUT = os.environ.get(
    "PRESS_OUT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "output", "week4"))
os.makedirs(OUT, exist_ok=True)

# ----------------------------------------------------------------------
# 工具
# ----------------------------------------------------------------------
def pct(sorted_xs, p):
    if not sorted_xs:
        return None
    idx = min(len(sorted_xs) - 1, int(round((p / 100) * (len(sorted_xs) - 1))))
    return round(sorted_xs[idx], 3)


def summarize(samples):
    s = sorted(samples)
    return {"n": len(s), "min": pct(s, 0), "p50": pct(s, 50), "p95": pct(s, 95),
            "max": pct(s, 100), "mean": round(statistics.mean(s), 3) if s else None}


# ----------------------------------------------------------------------
# 1. Hive 查询压测（分区裁剪 vs 全表）
# ----------------------------------------------------------------------
def run_hive(rounds=3, concurrency=3):
    from pyhive import hive  # noqa

    conf = dict(host=os.environ.get("HIVE_HOST", "localhost"),
                port=int(os.environ.get("HIVE_PORT", 10000)),
                username=os.environ.get("HIVE_USER", "hive"),
                database=os.environ.get("HIVE_DB", "dws"))

    SQL_PART = """
    select sum(pay_amount) from dwd.dwd_order
    where order_date between '2024-11-01' and '2024-11-30'
    """
    SQL_FULL = """
    select sum(case when order_date between '2024-11-01' and '2024-11-30'
               then pay_amount else 0 end) from dwd.dwd_order
    """

    def one_query(sql):
        t0 = time.time()
        conn = hive.connect(**conf)
        try:
            cur = conn.cursor()
            cur.execute(sql)
            cur.fetchone()
            cur.close()
        finally:
            conn.close()
        return round(time.time() - t0, 3)

    def bench(name, sql, rounds, concurrency):
        samples = []
        for _ in range(rounds):
            with cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
                samples += list(ex.map(lambda _: one_query(sql), range(concurrency)))
        return {"name": name, **summarize(samples)}

    print("== Hive 查询压测（分区裁剪 vs 全表扫描）==")
    part = bench("分区裁剪(2024-11)", SQL_PART, rounds, concurrency)
    full = bench("全表扫描(2024-11)", SQL_FULL, rounds, concurrency)
    return [part, full]


# ----------------------------------------------------------------------
# 2. 大屏 API HTTP 压测（仅标准库）
# ----------------------------------------------------------------------
def run_http(url="http://127.0.0.1:8080/api/all", rounds=3, concurrency=10):
    import urllib.request

    def one(_):
        t0 = time.time()
        with urllib.request.urlopen(url, timeout=30) as resp:
            resp.read()
        return round((time.time() - t0) * 1000, 1)  # ms

    print(f"== 大屏 API 压测（{url}）==")
    samples = []
    for _ in range(rounds):
        with cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
            samples += list(ex.map(one, range(concurrency)))
    r = {"name": "HTTP GET /api/all", "unit": "ms", **summarize(samples)}
    r["throughput_rps"] = round(len(samples) / (sum(samples) / 1000), 1) if sum(samples) else None
    return [r]


# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hive", action="store_true")
    ap.add_argument("--http", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=3)
    args = ap.parse_args()

    results = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "hive": [], "http": []}
    if args.all or args.hive:
        results["hive"] = run_hive(args.rounds, args.concurrency)
    if args.all or args.http:
        results["http"] = run_http(rounds=args.rounds,
                                   concurrency=max(args.concurrency, 10))

    out_path = os.path.join(OUT, "press_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n== 摘要 ==")
    for grp in ("hive", "http"):
        for r in results[grp]:
            print(f"{r['name']}: n={r['n']} p50={r['p50']}s p95={r['p95']}s max={r['max']}s"
                  + (f" QPS={r.get('throughput_rps')}" if r.get("throughput_rps") else ""))
    print("\n结果已写入", out_path)


if __name__ == "__main__":
    main()
