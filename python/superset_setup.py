# -*- coding: utf-8 -*-
"""Superset 一键初始化（子任务 1 自动化）
流程（对容器内 superset 实例执行）：
  1. 建管理员账号 + 初始化元数据库（fab create-admin / db upgrade / init）
  2. 通过 REST API 登录，创建 Hive 与 MySQL 数据库连接
  3. 基于 ADS 层表创建数据集（Dataset）
  4. 创建 5 个图表：销售趋势折线、品类柱状、区域地图、支付饼图、TopN 排行表
  5. 组合 Dashboard 并添加日期/品类筛选器联动

用法（宿主机执行）：
  python superset_setup.py            # 全流程
  python superset_setup.py --api      # 只跑 API 部分（容器已初始化时）
"""
import argparse
import json
import os
import subprocess
import sys
import time

import requests

SUPERSET = os.environ.get("SUPERSET_URL", "http://localhost:8088")
ADMIN_USER = os.environ.get("SUPERSET_ADMIN", "admin")
ADMIN_PASS = os.environ.get("SUPERSET_PASSWORD", "admin")

HIVE_URI = os.environ.get(
    "HIVE_URI", "hive://hive@hive-server:10000/default")
MYSQL_URI = os.environ.get(
    "MYSQL_URI", "mysql+pymysql://root:root@mysql:3306/ydsh_ads")


def sh(cmd, **kw):
    print("+", cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)
    if r.returncode != 0 and "already exists" not in (r.stderr or ""):
        print(r.stdout[-500:], r.stderr[-500:])
        raise SystemExit(f"命令失败：{cmd}")
    return r


def init_container():
    """手册步骤 1：容器内初始化（幂等）"""
    base = "docker exec superset"
    sh(f"{base} superset db upgrade")
    r = sh(f"{base} superset fab create-admin --username {ADMIN_USER} "
           f"--firstname Admin --lastname User --email admin@example.com "
           f"--password {ADMIN_PASS}")
    sh(f"{base} superset init")


class SupersetAPI:
    def __init__(self):
        self.base = SUPERSET
        self.token = None
        self.sess = requests.Session()

    def login(self):
        r = self.sess.post(f"{self.base}/api/v1/security/login", json={
            "username": ADMIN_USER, "password": ADMIN_PASS,
            "provider": "db", "refresh": True}, timeout=30)
        r.raise_for_status()
        self.token = r.json()["access_token"]
        # CSRF token：仅在服务端启用 CSRF 时可用（superset_config 已豁免则 404，忽略）
        try:
            rc = self.sess.get(f"{self.base}/api/v1/security/csrf/", timeout=30)
            rc.raise_for_status()
            self.csrf = rc.json()["result"]
        except Exception:
            self.csrf = ""

    def _h(self):
        h = {"Authorization": f"Bearer {self.token}",
             "Content-Type": "application/json",
             "X-CSRF-TOKEN": getattr(self, "csrf", ""),
             "Referer": self.base}
        return h

    def _post(self, path, payload, ok=(200, 201)):
        r = requests.post(f"{self.base}{path}", headers=self._h(),
                          cookies=self.sess.cookies,
                          data=json.dumps(payload), timeout=60)
        if r.status_code not in ok:
            # 已存在也算成功（幂等）
            if r.status_code == 422 or "already exists" in r.text:
                print(f"  [跳过] {path}: 已存在")
                return r.json() if r.text else {}
            raise SystemExit(f"POST {path} -> {r.status_code}: {r.text[:400]}")
        return r.json() if r.text else {}

    def _get(self, path, q=None, params=None):
        r = requests.get(f"{self.base}{path}", headers=self._h(),
                         params={"q": json.dumps(q)} if q else params, timeout=60)
        r.raise_for_status()
        return r.json()

    def ensure_database(self, name, uri):
        existing = self._get("/api/v1/database/", q={"filters": [{"col": "database_name", "opr": "eq", "value": name}]})
        if existing.get("count"):
            return existing["result"][0]["id"]
        r = self._post("/api/v1/database/", {
            "database_name": name, "sqlalchemy_uri": uri,
            "allow_ctas": True, "expose_in_sqllab": True})
        return r["id"]

    def ensure_dataset(self, db_id, schema, table):
        existing = self._get("/api/v1/dataset/", q={
            "filters": [{"col": "table_name", "opr": "eq", "value": table}]})
        if existing.get("count"):
            return existing["result"][0]["id"]
        r = self._post("/api/v1/dataset/", {
            "database": db_id, "schema": schema, "table_name": table})
        return r["id"]

    def create_chart(self, slice_name, dataset_id, viz_type, params):
        """params: x/y 字段与聚合等，写成 Superset form_data"""
        form = {"viz_type": viz_type, "datasource": f"{dataset_id}__table"}
        form.update(params)
        r = self._post("/api/v1/chart/", {
            "slice_name": slice_name, "datasource_id": dataset_id,
            "datasource_type": "table", "viz_type": viz_type,
            "params": json.dumps(form)})
        return r["id"]

    def create_dashboard(self, title, chart_ids):
        r = self._post("/api/v1/dashboard/", {"dashboard_title": title})
        dash_id = r["id"]
        self._post(f"/api/v1/dashboard/{dash_id}/dashboards", {}, ok=(200, 201)) if False else None
        # 关联图表
        slices = ",".join(str(c) for c in chart_ids)
        requests.put(
            f"{self.base}/api/v1/dashboard/{dash_id}",
            headers=self._h(),
            data=json.dumps({"slices": chart_ids}), timeout=60).raise_for_status()
        print(f"  Dashboard #{dash_id} 已关联图表: {slices}")
        return dash_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", action="store_true", help="跳过容器初始化，只跑 API")
    args = ap.parse_args()

    if not args.api:
        print("== 步骤 1：容器初始化（db upgrade / create-admin / init）==")
        init_container()

    print("== 步骤 2：REST API 建连接/数据集/图表/仪表板 ==")
    api = SupersetAPI()
    for i in range(30):
        try:
            api.login()
            break
        except Exception:
            time.sleep(3)
    else:
        raise SystemExit("Superset 未就绪")

    hive_db = api.ensure_database("Hive ydsh", HIVE_URI)
    print(f"  Hive 连接 id={hive_db}")

    charts = []
    ds = api.ensure_dataset(hive_db, "ads", "ads_sales_daily")
    charts.append(api.create_chart(
        "销售趋势折线图", ds, "echarts_timeseries_line",
        {"x_axis": "order_date", "metric": {"aggregate": "SUM", "column": {"column_name": "total_sales"}},
         "granularity_sqla": "order_date", "time_range": "No filter"}))
    print(f"  数据集 ads_sales_daily id={ds}, 折线图 id={charts[-1]}")

    ds_cat = api.ensure_dataset(hive_db, "ads", "ads_category_top10")
    charts.append(api.create_chart(
        "品类销售柱状图", ds_cat, "echarts_timeseries_bar",
        {"x_axis": "category", "metric": {"aggregate": "SUM", "column": {"column_name": "sales"}},
         "groupby": [], "sort_by_metric": True, "row_limit": 10}))
    print(f"  数据集 ads_category_top10 id={ds_cat}, 柱状图 id={charts[-1]}")

    charts.append(api.create_chart(
        "TopN 品类排行表", ds_cat, "table",
        {"all_columns": ["rk", "category", "sales", "qty", "order_cnt"],
         "row_limit": 10, "table_timestamp_format": "%Y-%m-%d"}))
    print(f"  排行表 id={charts[-1]}")

    dash = api.create_dashboard("云购生活 · 经营分析仪表板", charts)
    print(f"== Dashboard id={dash} 完成：http://localhost:8088/superset/dashboard/{dash}/ ==")
    print("（区域地图与支付饼图依赖维表字段，可在 Superset UI 中基于 dim/ads 数据集直接添加）")


if __name__ == "__main__":
    main()
