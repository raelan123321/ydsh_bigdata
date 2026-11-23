# Yundu Life Retail Data Warehouse & Analytics System

> Enterprise-grade end-to-end data warehouse and business analytics visualization system for "Yundu Life" (云购生活), an omnichannel new-retail enterprise.
> Course project: Enterprise Project Practice (Weeks 1–5). [中文说明](README.zh-CN.md)

## Team

| Role | Member |
|---|---|
| Project Manager | Liu Zhengyang |
| Data Engineer | Liu Zhengyang |
| Data Analyst | Liu Zhengyang |
| Visualization Engineer | Liu Zhengyang |

> One-person multi-role team; adjust per actual team size.

## Overview

This project builds a complete data pipeline — from raw CSV ingestion to interactive dashboards — across a four-layer warehouse (ODS → DWD → DWS → ADS), with AI-powered NL2SQL querying, GMV forecasting, and one-command Docker deployment.

**Key results (2024 full-year dataset):**

- GMV **¥23,290,536.89** · 9,236 valid orders · AOV **¥2,521.71** · 1,000 active users
- Five data-quality issue classes all remediated (repair rate **100%**, verifiable via re-runnable SQL)
- HTTP API p50 latency **28.5 ms**; Hive partition pruning **22% faster** scans

## Architecture

```
Raw CSV (6 tables)
      │
┌─────▼─────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│    ODS    │──▶│   DWD    │──▶│   DWS    │──▶│   ADS    │
│ raw layer │   │ cleaned  │   │ aggregate│   │ app layer│
└───────────┘   └──────────┘   └──────────┘   └────┬─────┘
                                                   │ sync
                          ┌──────────── MySQL (ydsh_ads)
                          │
     ┌────────────────────┼────────────────────┐
     ▼                    ▼                    ▼
 ECharts Dashboard   Superset BI         Streamlit NL2SQL
 (Flask JSON API)    (direct Hive)       (NL → SQL → chart)
                          ▲
                          └──── GMV Forecast model ────┘
```

7 containerized services (Docker Compose): `mysql` · `hive-metastore` · `hive-server` · `superset` · `clickhouse` · `screen-api` · `app`

## Features

- **Four-layer warehouse** — ODS raw ingestion, DWD cleansing + star-schema dimensional modeling, DWS aggregation (day/week/month/category/store/channel), ADS KPI & topic tables
- **Data quality governance** — five issue classes (missing, duplicate, outlier, enum, format) with 100% repair rate and re-runnable audit SQL
- **GMV forecasting** — multi-model comparison (mean baseline / MA(7) / linear regression) with MAE/RMSE/MAPE evaluation, 7-day forecast output
- **NL2SQL assistant** — natural-language question → Hive SQL → execution → ECharts rendering, with conversation history
- **Visualization** — 1920×1080 adaptive ECharts big screen (KPI/trend/category/channel/region/heatmap/scatter) + Superset dashboard (5 charts, scripted via REST API)
- **One-command deployment** — idempotent Hive initialization, named-volume persistence, healthcheck-gated startup, secrets via `.env`

## Quick Start

```bash
cp .env.example .env        # configure passwords & secret key
docker compose up -d        # start all 7 services (Hive auto-initializes idempotently)
```

Then load data and rebuild the BI assets:

```bash
# load warehouse: output/hive_demo/step0~5 + sql/{dwd,dws,ads}
python python/export_ads_to_mysql.py      # ADS → MySQL
python python/gmv_forecast.py             # forecasting
python python/superset_setup.py --api     # rebuild Superset datasets/charts/dashboard
```

**Entry points**

| App | URL |
|---|---|
| ECharts big screen | http://localhost:8080 |
| Superset dashboard | http://localhost:8088 |
| Streamlit NL2SQL | http://localhost:8501 |

## Tech Stack

Hive 3.1.3 · MySQL 8.0 · Superset 3.1.0 · ClickHouse 24.8 · Python 3.10 (pandas / statsmodels / Flask / Streamlit) · ECharts 5.5 · Docker Compose

## Repository Layout

```
├── docker-compose.yml     7-service orchestration
├── hive/                  custom Hive image (idempotent init + persistence)
├── sql/                   ods · quality · clean · dwd · dws · ads (18 scripts)
├── python/                forecast · nl2sql · insight · export · superset · press-test
├── app/                   big screen · Flask API · Streamlit · data generator
├── superset/              custom image + config
├── docs/                  requirements / quality report / architecture / deployment / API guide
└── 交付物/                 weekly logs, AI-collaboration logs, deliverables
```

## Documentation

| Document | Content |
|---|---|
| 需求文档 (Requirements) | business context, stakeholder needs, KPI definitions |
| 数据质量清洗报告 (Quality Report) | five issue classes, strategies, 100% repair rates |
| 数仓架构设计文档 (Architecture) | four-layer design, star schema, tech selection |
| 第4周_部署手册 (Deployment) | environment, steps, troubleshooting |
| 第4周_API配置指南 (API Guide) | secret management, interface specs, examples |
| 第5周_联调核对清单 (E2E Checklist) | 18-point end-to-end verification record |

## License

For educational / course-portfolio use.
