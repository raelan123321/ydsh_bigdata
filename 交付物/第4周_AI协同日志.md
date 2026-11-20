# 第 4 周 AI 协同日志

> 项目：云购生活新零售企业——企业级数据仓库与经营分析可视化系统
> 成员：刘正扬　周期：第 4 周（可视化实现 · 项目部署）

| # | 日期 | 任务 | AI 工具 | 提示词（要点） | AI 产出 | 人工决策与修正 | 收获 |
|---|------|------|---------|----------------|---------|----------------|------|
| 1 | 11-18 | 解析第 4 周任务书与部署手册，拆解 5 个子任务与 6 项交付物 | WorkBuddy（文档解析） | "解析这两份第 4 周文档" | 子任务清单、交付物评分表、与前三周资产的衔接分析、5 个风险预警 | 确认推进顺序：编排→大屏/Superset→Streamlit→压测手册 | 先读任务书再动手，避免返工 |
| 2 | 11-19 | 扩展 docker-compose.yml（新增 superset / clickhouse / screen-api / app 四服务） | WorkBuddy（代码生成） | "按手册要求编排全部服务，密钥走环境变量" | compose 编排草案 + .env.example + 两个 Dockerfile | ① 将 build: 改为显式 image: 引用预构建镜像，避免 up 触发重建；② ClickHouse 健康检查补密码认证 | depends_on + healthcheck 是编排稳定性的关键 |
| 3 | 11-19 | 容器镜像构建连续失败排查 | WorkBuddy（错误诊断） | 粘贴构建报错日志 | 定位三类问题：sasl 需 C++ 编译、apt 国外源超时、pip extra 依赖连锁拉 sasl | ① 改用 pure-sasl 纯 Python 实现，删除整个 apt 编译层；② pip 清华源；③ pyhive 不带 [hive] extra 手工补 thrift | "删依赖"有时比"补环境"更有效 |
| 4 | 11-19 | ECharts 数据大屏开发（6 类图表 + scale 自适应） | WorkBuddy（代码生成 + 数据处理） | "基于 ADS/KPI 数据出折线、柱状、散点、热力、地图" | index.html 大屏页 + screen_api.py Flask 接口 + gen_data.py 预生成 7 组 JSON | 时段×品类热力图需从明细表实时聚合，确认金额分摊口径后生成；地图 GeoJSON 改用国内镜像下载 | 大屏美观的前提是数据口径先对齐 |
| 5 | 11-20 | Superset 自动化配置（数据源/数据集/5 图表/Dashboard） | WorkBuddy（API 脚本生成） | "用 REST API 一键建好仪表板，不要手工点 UI" | superset_setup.py + superset_dashboard_layout.py | ① 遭遇 CSRF 拦截，演示环境关闭 WTF_CSRF 并注释"生产必须恢复"；② dashboard 关联图表 400，改用 position_json v2 布局；③ 中国省级地图 Superset 支持弱，改省份柱状图、真地图放 ECharts 大屏 | UI 能点的不一定能自动化；position_json 是 Superset 3.x 布局正解 |
| 6 | 11-20 | 元数据丢失后 Hive 全链路恢复（12 个 SQL 依序重跑） | WorkBuddy（自动化脚本） | "重建容器后检查数据，缺的补齐" | 恢复脚本按 ODS→DWD→DWS→ADS 顺序执行，15,000 单全量回灌 | ① Git Bash 路径转换坑（MSYS2_ARG_CONV_EXCL）；② step1 是侦察演示 SQL，失败属预期不应中断链路；③ 恢复后行数与第 3 周 KPI 勾稽一致 | 容器无卷 = 数据裸奔，元数据必须挂持久卷 |
| 7 | 11-20 | NL2SQL 接入 Streamlit 并容器内验证问答闭环 | WorkBuddy（代码集成 + 测试） | "容器内测试 2024年7月GMV、各渠道占比两个问题" | streamlit_app.py（历史对话/加载状态/ECharts 内联渲染/错误提示）+ 容器内实测通过 | import 冲突修正为把 nl2sql 子目录加入 sys.path；规则兜底 10/10 保持 | 无 LLM Key 也要保证闭环可演示 |
| 8 | 11-20 | 并发压测与结果解读 | WorkBuddy（脚本生成 + 分析） | "分区 vs 全表、HTTP 并发 10，各 3 轮" | press_test.py + 两份结果 JSON | 分区裁剪 p50 1.12s 较全表 1.42s 快约 22%；HTTP p50 28.5ms / 14.3 QPS | 优化要有对照组数据支撑，不能凭感觉说"变快了" |

**本周小结**：AI 承担了脚本生成、错误定位与批量验证等重体力工作，人负责口径决策、安全边界（CSRF/密钥）与演示效果取舍；"实跑验证 + 勾稽对账"始终是最后一道关。
