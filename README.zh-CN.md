# 云购生活数据仓库项目

> 云购生活新零售企业——企业级数据仓库与经营分析可视化系统
> 课程：企业项目实战实训（第 1~4 周）

## 团队信息

- **队名**：____（待填写）
- **成员**：刘正扬
- **口号**：____（待填写）

## 角色分工

- 项目经理：刘正扬
- 数据工程师：刘正扬
- 数据分析师：刘正扬
- 可视化工程师：刘正扬

> 一人多岗（团队规模 2~3 人时按实际情况调整）。

## 项目目标

围绕云购生活新零售业务，搭建**从贴源到看板**的完整数据链路：

1. 大数据基础环境容器化（Docker / Hive / MySQL / Superset / ClickHouse）；
2. 6 张业务模拟数据（用户、商品、门店、订单、订单明细、用户行为）接入 ODS 贴源层；
3. 建立数据质量评估体系（完整性 / 唯一性 / 有效性 / 一致性 / 准确性五维度）；
4. 完成 ODS → DWD → DWS → ADS 四层数仓建设与核心 KPI 计算；
5. 在 ADS 之上完成预测建模、NL2SQL 智能问答、AI 洞察与可视化仪表板；
6. 一键部署成可稳定演示的系统。

## 系统架构

```
              ┌──────────────────── Docker Compose ────────────────────┐
 浏览器:8088 → │ superset(BI) ──hive://hive-server:10000──▶ hive-server │
 浏览器:8080 → │ screen-api(Flask) ── JSON ──▶ ECharts 大屏              │
 浏览器:8501 → │ app(Streamlit) ── NL2SQL ──▶ hive-server                │
 浏览器:8123 → │ clickhouse(OLAP 预留)                                   │
              │        mysql:3306（metastore 元数据 + ADS 结果库）        │
              └────────────────────────────────────────────────────────┘
```

| 服务 | 端口 | 职责 |
|---|---|---|
| mysql | 3306 | Hive metastore 元数据库 / ADS 结果库 |
| hive-metastore | 9083 | 元数据服务 |
| hive-server | 10000 / 10002 | HiveServer2（JDBC / pyhive） |
| superset | 8088 | BI 仪表板（5 图表 + Dashboard） |
| clickhouse | 8123 / 9000 | OLAP 引擎（预留） |
| screen-api | 8080 | 大屏 JSON 接口 + 静态页面 |
| app | 8501 | Streamlit 智能问答 |

## 技术栈

- **容器化**：Docker Desktop + Docker Compose（7 服务，healthcheck 控制启动序）
- **数据仓库**：Apache Hive 3.1.3（Tez）+ MySQL 8.0 metastore，四层 ODS/DWD/DWS/ADS，ORC + 动态分区
- **数据处理**：Hive SQL（窗口函数去重、缺失值填充、RFM 分层、分位数）、Python（pandas / pyhive）
- **分析与建模**：均值基线 / MA7 / 线性回归 / XGBoost 对比，MAE / MAPE / R²
- **智能问答**：LangChain + OpenAI 兼容协议（DeepSeek / Qwen）+ 规则兜底，NL2SQL 全链路
- **可视化**：Apache Superset 3.1（REST API 自动化建 Dashboard）+ ECharts 5.5（1920×1080 scale 自适应大屏）+ Streamlit
- **版本管理**：Git + GitHub（feat: / docs: 提交规范，PR + Code Review 留痕）

## 数仓分层

| 层 | 内容 | 关键表 |
|---|---|---|
| ODS | 6 张业务表原样落地 | ods_order（15,000 单）、ods_order_item、ods_user、ods_product、ods_store、ods_user_behavior |
| DWD | 清洗 + 维表 + 标准化 | dim_user / dim_product / dim_store、dwd_order、dwd_order_item、dwd_order_norm（6 状态 / 4 渠道标准化） |
| DWS | 六维汇总 | dws_sales_day / week / month、dws_category、dws_store、dws_channel |
| ADS | 应用指标 | ads_sales_daily、ads_category_top10、ads_user_value(RFM)、ads_region、ads_channel、KPI 5 项 |

**核心指标（有效订单口径）**：GMV 23,290,536.89 元 / 9,236 单 / AOV 2,521.71 元 / 活跃用户 1,000 / 月度复购率 28.68%~34.31%

## 阶段进度

| 周次 | 主题 | 产出 | 状态 |
|---|---|---|---|
| 第 1 周 | 项目启动 · 环境搭建 · Git · ODS 导入与清洗（一） | 容器环境、ODS 6 表、质量预评估表 | ✅ |
| 第 2 周 | 清洗（二）· 星型模型 · EDA | 3 份 docx 报告、AI 协同日志、Hive 实跑记录 | ✅ |
| 第 3 周 | DWS/ADS · KPI · 预测建模 · NL2SQL · AI 洞察 | 6 张 DWS、3 张 ADS、5 项 KPI、预测报告、问答链路 | ✅ |
| 第 4 周 | Superset 仪表板 · ECharts 大屏 · Streamlit · Docker 一键部署 · 压测 | 见 `第4周_提交.zip`、`交付物/第4周_交付清单.md` | ✅ |

## 目录结构

```
ydsh_bigdata/
├── docker-compose.yml            # 7 服务编排（mysql/hive/superset/clickhouse/screen/app）
├── .env.example                  # 密钥模板（真实 .env 不入库）
├── sql/
│   ├── ods/                      # ODS 建表与数据加载
│   ├── quality/                  # 数据质量五维度检查
│   ├── clean/                    # 缺失值填充、去重、字段合并
│   ├── dwd/                      # 维表 + 事实表 + 明细清洗（08）
│   ├── dws/                      # 六维汇总（09）
│   └── ads/                      # 应用层指标、KPI、区域/渠道补充（10~12）
├── python/
│   ├── gmv_forecast.py           # GMV 预测（均值/MA7/线性回归）
│   ├── nl2sql/                   # Schema 抽取、Prompt、生成校验、评测
│   ├── ai_insight.py             # 异常检测 + 归因 + 自动报告
│   ├── export_ads_to_mysql.py    # Hive ADS → MySQL 导数
│   ├── superset_setup.py         # Superset REST 自动建数据源/数据集/图表
│   └── press_test.py             # 分区 vs 全表、HTTP 并发压测
├── app/
│   ├── screen/                   # ECharts 大屏（index.html + 本地 echarts/GeoJSON）
│   ├── screen_api.py             # 大屏 JSON 接口（Flask）
│   ├── streamlit_app.py          # 智能问答（NL2SQL 闭环 + 图表渲染）
│   └── gen_data.py               # 大屏数据预生成
├── superset/                     # 自建镜像（内置 pyhive）+ superset_config.py
├── docs/                         # 各周报告 docx、部署手册、API 配置指南、压测记录
├── 交付物/                        # 周志、AI 协同日志、交付清单、截图
└── 交付数据/                      # KPI 结果表与各维度 CSV
```

## 快速开始

```bash
# 1. 准备密钥（真实值只留在本地 .env）
cp .env.example .env

# 2. 一键启动全部服务（首次自动构建镜像，hive-server 约需 2~3 分钟变 healthy）
docker compose up -d
docker compose ps

# 3. 执行数仓脚本（首次或元数据丢失后，按顺序）
#    ODS → clean → dwd → dws → ads，脚本位于 sql/ 各目录

# 4. Superset 初始化与自动建仪表板
docker exec superset superset db upgrade
docker exec superset superset fab create-admin --username admin \
  --firstname Admin --lastname User --email admin@example.com --password admin
docker exec superset superset init
python python/superset_setup.py
```

访问入口：Superset http://localhost:8088（admin/admin）· 大屏 http://localhost:8080 · 问答 http://localhost:8501

## 文档索引

| 文档 | 位置 |
|---|---|
| 数据质量对比报告 | `docs/数据质量对比报告.docx` |
| 数仓架构设计文档 | `docs/数仓架构设计文档.docx` |
| 探索性分析简报 | `docs/探索性分析简报.docx` |
| 预测建模分析报告 | `docs/预测建模分析报告.docx` |
| AI 智能洞察与反思 | `docs/AI智能洞察与反思.docx` |
| 第 4 周部署手册 | `docs/第4周_部署手册.docx` |
| 第 4 周 API 配置指南 | `docs/第4周_API配置指南.docx` |
| 各周周志 / AI 协同日志 | `交付物/` |
| PR 说明 / Code Review / Issue | `docs/collaboration/` |
