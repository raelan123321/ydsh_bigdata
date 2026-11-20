# -*- coding: utf-8 -*-
"""云购生活 · 经营数据大屏后端
提供 JSON 数据接口 + 大屏静态页面（ECharts 前端渲染）
数据源：app/data/*.json（由 gen_data.py 从第 3 周 KPI 结果与模拟数据预生成）

接口清单：
  GET /                  大屏页面
  GET /api/all           全量数据（大屏一次拉取）
  GET /api/kpi           KPI 摘要卡片
  GET /api/month_trend   月度 GMV 趋势（折线）
  GET /api/category      品类 Top10（柱状）
  GET /api/channel       渠道占比（饼图）
  GET /api/region        区域分布（地图）
  GET /api/heatmap       时段×品类（热力图）
  GET /api/scatter       月度 GMV-订单量（散点）
"""
import json
import os

from flask import Flask, jsonify, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
SCREEN_DIR = os.path.join(HERE, "screen")

app = Flask(__name__)

_FILES = [
    "kpi", "month_trend", "category", "channel", "region", "heatmap", "scatter",
]


def _load(name):
    with open(os.path.join(DATA_DIR, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


@app.get("/")
def index():
    return send_from_directory(SCREEN_DIR, "index.html")


@app.get("/echarts.min.js")
def echarts_js():
    return send_from_directory(SCREEN_DIR, "echarts.min.js")


@app.get("/china.json")
def china_geo():
    return send_from_directory(SCREEN_DIR, "china.json")


@app.get("/api/all")
def api_all():
    return jsonify({name: _load(name) for name in _FILES})


@app.get("/api/<name>")
def api_one(name):
    if name not in _FILES:
        return jsonify({"error": f"unknown dataset: {name}"}), 404
    return jsonify(_load(name))


if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", 8080))
    app.run(host=host, port=port, debug=False)
