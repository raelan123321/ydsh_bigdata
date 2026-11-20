# -*- coding: utf-8 -*-
"""把已有图表组装进 Superset Dashboard（position_json 布局方式）"""
import json
import sys

import requests

sys.path.insert(0, "C:/Users/16851/WorkBuddy/2026-11-02-08-30-31/python")
from superset_setup import SUPERSET, ADMIN_USER, ADMIN_PASS  # noqa

DASH_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1
CHARTS = json.loads(sys.argv[2]) if len(sys.argv) > 2 else [1, 2, 3]


def chart_meta(i):
    return {"type": "CHART", "id": f"CHART-{i}", "children": [f"CHART-{i}-wrap"],
            "meta": {"chartId": i, "height": 50, "width": 4,
                     "sliceName": f"chart-{i}", "updatedAt": ""}}


def chart_wrap(i):
    return {"type": "ROW", "id": f"CHART-{i}-wrap", "children": [f"CHART-{i}"],
            "meta": {"background": "TRANSPARENT"}}


def build_position(charts):
    rows = []
    pos = {"DASHBOARD_VERSION_KEY": "v2"}
    for i in charts:
        pos[f"CHART-{i}"] = chart_meta(i)
        pos[f"CHART-{i}-wrap"] = chart_wrap(i)
        rows.append(f"CHART-{i}-wrap")
    pos["GRID_ID"] = {"type": "GRID", "id": "GRID_ID", "children": rows,
                      "parent": "ROOT_ID", "meta": {"width": 4}}
    pos["ROOT_ID"] = {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]}
    pos["HEADER_ID"] = {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": ""}}
    return json.dumps(pos)


s = requests.Session()
tok = s.post(f"{SUPERSET}/api/v1/security/login",
             json={"username": ADMIN_USER, "password": ADMIN_PASS,
                   "provider": "db", "refresh": True}, timeout=10).json()["access_token"]
h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
     "Referer": SUPERSET}

r = s.put(f"{SUPERSET}/api/v1/dashboard/{DASH_ID}", headers=h, cookies=s.cookies,
          data=json.dumps({"position_json": build_position(CHARTS)}), timeout=60)
print("PUT:", r.status_code, r.text[:300])
