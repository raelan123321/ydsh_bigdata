# -*- coding: utf-8 -*-
"""ADS 层结果导出到 MySQL（供 Superset 连接 ydsh_ads 库做仪表板）
流程：Hive 读取 ADS 三表 → MySQL 建 ydsh_ads 库与表 → 分批写入
用法（w4-app 容器内）：python export_ads_to_mysql.py
"""
import os
import sys
import time

from pyhive import hive
import pymysql

HIVE = dict(host=os.environ.get("HIVE_HOST", "hive-server"),
            port=int(os.environ.get("HIVE_PORT", 10000)),
            username=os.environ.get("HIVE_USER", "hive"),
            database="ads")

MYSQL = dict(host=os.environ.get("MYSQL_HOST", "mysql"),
             port=3306,
             user=os.environ.get("MYSQL_USER", "root"),
             password=os.environ.get("MYSQL_ROOT_PASSWORD", "root"),
             charset="utf8mb4")

DDL_DB = "create database if not exists ydsh_ads default charset utf8mb4"

TABLES = {
    "ads_sales_daily": (
        """create table if not exists ydsh_ads.ads_sales_daily (
            order_date varchar(10), gmv double, order_cnt int, aov double,
            user_cnt int, dod_rate double, gmv_ma7 double)""",
        "select order_date, gmv, order_cnt, aov, user_cnt, dod_rate, gmv_ma7 from ads.ads_sales_daily"),
    "ads_category_top10": (
        """create table if not exists ydsh_ads.ads_category_top10 (
            rk int, category varchar(50), sales double, qty int, order_cnt int,
            sales_share double, cum_share double)""",
        "select rk, category, sales, qty, order_cnt, sales_share, cum_share from ads.ads_category_top10"),
    "ads_user_value": (
        """create table if not exists ydsh_ads.ads_user_value (
            user_id varchar(20), last_order_date varchar(10), recency_days int,
            frequency int, monetary double, r_score int, f_score int, m_score int,
            rfm_score int, segment varchar(20))""",
        "select user_id, last_order_date, recency_days, frequency, monetary, "
        "r_score, f_score, m_score, rfm_score, segment from ads.ads_user_value"),
}


def hive_fetch(sql):
    conn = hive.connect(**HIVE)
    cur = conn.cursor()
    cur.execute(sql)
    cols = [d[0].split(".")[-1] for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return cols, rows


def main():
    t0 = time.time()
    my = pymysql.connect(database=None, **MYSQL)
    cur = my.cursor()
    cur.execute(DDL_DB)
    cur.close()
    my.close()

    for table, (ddl, query) in TABLES.items():
        print(f"[{table}] 从 Hive 读取 …")
        cols, rows = hive_fetch(query)
        print(f"[{table}] {len(rows)} 行")

        conn = pymysql.connect(database="ydsh_ads", **MYSQL)
        cur = conn.cursor()
        cur.execute(f"drop table if exists ydsh_ads.{table}")
        cur.execute(ddl)
        ph = ",".join(["%s"] * len(cols))
        cur.executemany(f"insert into ydsh_ads.{table} values ({ph})", rows)
        conn.commit()
        cur.close()
        conn.close()
        print(f"[{table}] 写入 MySQL 完成")

    print(f"全部导出完成，耗时 {round(time.time()-t0,1)}s")


if __name__ == "__main__":
    sys.exit(main())
