# -*- coding: utf-8 -*-
"""云购生活 · 智能经营问答（Streamlit）
接入第 3 周 NL2SQL 后端，实现闭环：
  提问 → 生成 SQL（LLM / 规则兜底）→ 安全校验 → Hive 执行 → 结果展示 → ECharts 图表渲染
交互增强：历史对话侧栏、加载状态（spinner）、错误提示、示例问题、自动图表推荐
预测增强：任意 horizon 的 GMV 预测问答（"预测未来1天/8天/30天GMV"），实时调用 gmv_forecast 模型
运行：streamlit run streamlit_app.py --server.port=8501
"""
import json
import os
import re
import sys

import pandas as pd
import streamlit as st

# 让容器/本地都能找到 python/nl2sql（compose 挂载在 /opt/project/python）
_HERE = os.path.dirname(os.path.abspath(__file__))
for _base in (os.path.join(_HERE, "..", "python"), "/opt/project/python"):
    if os.path.isdir(os.path.join(_base, "nl2sql")) and _base not in sys.path:
        sys.path.insert(0, _base)
        # nl2sql.py 与同名目录平级共存，把目录本身也加入才能 import 到模块
        _d = os.path.join(_base, "nl2sql")
        if _d not in sys.path:
            sys.path.insert(0, _d)
        break

try:
    from nl2sql import NL2SQL  # 第 3 周链路：生成 SQL + guard + pyhive 执行
except ImportError:
    NL2SQL = None

st.set_page_config(page_title="云购生活 · 智能经营问答", page_icon="🛒", layout="wide")

# ----------------------------------------------------------------------
# 页面样式（深色科技风，与大屏视觉统一）
# ----------------------------------------------------------------------
st.markdown("""
<style>
  .stApp { background: linear-gradient(180deg, #0a1128 0%, #060b1f 100%); }
  h1, h2, h3, p, span, label { color: #cfe6ff !important; }
  h1 { letter-spacing: 3px; }
  [data-testid="stSidebar"] { background: #0a1430; }
  .stTextInput input { background: rgba(10,20,48,.8) !important; color: #eaf6ff !important;
    border: 1px solid rgba(0,229,255,.35) !important; }
  .stButton>button { border: 1px solid rgba(0,229,255,.4) !important; color: #00e5ff !important;
    background: transparent !important; border-radius: 6px; }
  .stCodeBlock { border: 1px solid rgba(0,229,255,.2); }
</style>
""", unsafe_allow_html=True)

st.title("🛒 云购生活 · 智能经营问答")
st.caption("NL2SQL 闭环：自然语言 → SQL → Hive 执行 → 图表渲染　（无 LLM Key 时自动走规则兜底）")

# ----------------------------------------------------------------------
# 会话状态
# ----------------------------------------------------------------------
if "history" not in st.session_state:
    st.session_state.history = []   # [(question, sql, df_or_None, error_or_None, chart_type)]
if "_nl2sql" not in st.session_state or st.session_state._nl2sql is None:
    # 初始化失败不永久缓存：Hive 就绪后页面重跑会自动重试
    st.session_state._nl2sql = None
    st.session_state._init_err = ""
    try:
        st.session_state._nl2sql = NL2SQL(offline=True) if NL2SQL else None
    except Exception as e:  # Hive 未启动时也能进界面
        st.session_state._init_err = str(e)

EXAMPLES = [
    "2024年7月的GMV是多少",
    "各渠道销售额占比",
    "销售额最高的10个品类",
    "月度复购率",
    "各区域销售额排名",
    "未来7天GMV预测",
    "预测未来30天GMV",
]

# ----------------------------------------------------------------------
# GMV 预测问答：命中预测意图时，按问句中的天数实时调用 gmv_forecast 模型
#   · "未来7天GMV预测"          → 读取第 3 周落盘产物（output/forecast/forecast_day.csv）
#   · "预测未来1天/8天/30天GMV" → 用同一套模型（按 MAE 选优）实时外推任意 horizon
# 数据源 dws.dws_sales_day，与报表/问答口径同源（对应答辩 PPT 第 10 页）
# ----------------------------------------------------------------------
FORECAST_DIRS = (
    os.path.join(_HERE, "..", "output", "forecast"),
    "/opt/project/output/forecast",
)

_NUM2WORD = {"一周": 7, "下周": 7, "半个月": 15, "半月": 15, "一个月": 30, "次月": 30,
             "一季度": 90, "半年": 180, "一年": 365, "全年": 365}


def _parse_horizon(q: str) -> int:
    """从问句解析预测天数：'8天'/'未来30天' 直接取数字；'一周/一个月'等中文映射；默认 7 天，上限 365"""
    m = re.search(r"(\d+)\s*天", q) or re.search(r"(\d+)\s*日", q)
    if m:
        n = int(m.group(1))
    else:
        n = next((v for k, v in _NUM2WORD.items() if k in q), 7)
    return max(1, min(n, 365))


def _forecast_dir():
    for d in FORECAST_DIRS:
        if os.path.isdir(d):
            return d
    return None


def is_forecast_question(q: str) -> bool:
    low = q.lower()
    if "预测" in q or "forecast" in low:
        return True
    return "未来" in q and any(k in low for k in ("gmv", "销售额", "成交", "营业额"))


def _load_forecast_assets():
    """返回 (7天产物DataFrame或None, 历史序列DataFrame, metrics字典, 目录路径或None)"""
    base = _forecast_dir()
    if not base:
        return None, None, {}, None
    try:
        fpath = os.path.join(base, "forecast_day.csv")
        fday = pd.read_csv(fpath, encoding="utf-8-sig") if os.path.exists(fpath) else None
        hist = pd.read_csv(os.path.join(base, "series_history_day.csv"), encoding="utf-8-sig")
        mpath = os.path.join(base, "metrics.json")
        metrics = json.load(open(mpath, encoding="utf-8")) if os.path.exists(mpath) else {}
        return fday, hist, metrics, base
    except Exception:
        return None, None, {}, base


def _forecast_any_horizon(hist: pd.DataFrame, horizon: int, model: str):
    """复用 python/gmv_forecast.py 的模型，对任意 horizon 实时外推；导入失败时退化为均值外推"""
    try:
        sys.path.insert(0, os.path.join(_HERE, "..", "python"))
        sys.path.insert(0, "/opt/project/python")
        import gmv_forecast as gf
        dfm = hist[["order_date", "gmv"]].copy()
        dfm["order_date"] = pd.to_datetime(dfm["order_date"])
        fc = gf.forecast(dfm, horizon=horizon, model=model)
        fc["order_date"] = pd.to_datetime(fc["order_date"]).dt.strftime("%Y-%m-%d")
        return fc[["order_date", "gmv_pred"]], model
    except Exception:
        last = pd.to_datetime(hist["order_date"].max())
        dates = pd.date_range(last + pd.Timedelta(days=1), periods=horizon).strftime("%Y-%m-%d")
        level = round(float(hist["gmv"].mean()), 2)
        return pd.DataFrame({"order_date": dates, "gmv_pred": [level] * horizon}), "均值基线（内置退化）"


def render_forecast(q: str):
    """渲染 GMV 预测：历史末段 + N 天预测折线、预测明细表、模型评估表"""
    fday7, hist, metrics, base = _load_forecast_assets()
    if base is None or hist is None:
        st.error("未找到预测数据目录 output/forecast/，请先运行 python/gmv_forecast.py 生成")
        return None

    horizon = _parse_horizon(q)
    best = metrics.get("best_model", "均值基线")

    # 7 天默认问句 → 直接用落盘产物（与预测报告/PPT 数值一致）；其余 horizon → 实时外推
    if horizon == 7 and fday7 is not None:
        fday = fday7.copy()
        fday.columns = ["order_date", "gmv_pred"]
        used_model = f"{best}（第 3 周落盘产物）"
        source_note = "读取 output/forecast/forecast_day.csv"
    else:
        fday, used_model = _forecast_any_horizon(hist, horizon, best)
        source_note = f"实时调用 gmv_forecast.forecast(horizon={horizon})"

    # 模型评估表（三模型对比，按 MAE 选优）
    if metrics.get("metrics"):
        rows = []
        for name, m in metrics["metrics"].items():
            rows.append({"模型": name, "MAE(元)": round(m["MAE"], 2),
                         "RMSE(元)": round(m["RMSE"], 2), "MAPE": f"{m['MAPE(%)']}%"})
        best_mae = metrics["metrics"][best]["MAE"]
        st.markdown("**模型评估（留出验证：最后 14 天）：**")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(f"按 MAE 选优：{best}（MAE {best_mae:,.2f} 元）——日 GMV 围绕均值宽幅波动、无显著趋势，复杂模型反而拟合噪声")

    # 预测明细表
    st.markdown(f"**未来 {horizon} 天日粒度 GMV 预测（模型：{used_model}）：**")
    show = fday.copy()
    show["gmv_pred"] = pd.to_numeric(show["gmv_pred"]).round(2)
    st.dataframe(show, use_container_width=True, hide_index=True)

    # 历史末段 + 预测拼接折线（ECharts 双序列，预测段虚线）
    h = hist.tail(30)
    x = h["order_date"].astype(str).tolist() + fday["order_date"].astype(str).tolist()
    y_hist = h["gmv"].round(2).tolist() + [None] * len(fday)
    y_pred = [None] * (len(h) - 1) + [h["gmv"].iloc[-1].round(2)] + pd.to_numeric(fday["gmv_pred"]).round(2).tolist()
    js = _echarts_js()
    if js:
        cid = f"fc_{abs(hash(tuple(x))) % 99999}"
        html = f"""
        <div id="{cid}" style="width:100%;height:380px;"></div>
        <script>{js}</script>
        <script>
        const chart = echarts.init(document.getElementById('{cid}'), null, {{renderer:'canvas'}});
        chart.setOption({{
          backgroundColor: 'transparent',
          tooltip: {{ trigger: 'axis' }},
          legend: {{ data: ['历史日GMV', '预测日GMV'], textStyle: {{ color: '#cfe6ff' }}, top: 0 }},
          grid: {{ left: 70, right: 40, top: 40, bottom: 60 }},
          xAxis: {{ type:'category', data:{json.dumps(x)},
            axisLabel:{{ color:'#7fa3d9', rotate:30, fontSize:11 }},
            axisLine:{{ lineStyle:{{ color:'#2a4a80' }} }} }},
          yAxis: {{ type:'value', axisLabel:{{ color:'#7fa3d9' }},
            splitLine:{{ lineStyle:{{ color:'rgba(42,74,128,.35)', type:'dashed' }} }} }},
          series: [
            {{ type:'line', name:'历史日GMV', data:{json.dumps(y_hist)}, smooth:true,
               symbol:'none', connectNulls:false,
               lineStyle:{{ width:2.5, color:'#00e5ff' }}, itemStyle:{{ color:'#00e5ff' }},
               areaStyle:{{ color:'rgba(0,229,255,.18)' }} }},
            {{ type:'line', name:'预测日GMV', data:{json.dumps(y_pred)}, smooth:true,
               symbol:'circle', symbolSize:6, connectNulls:false,
               lineStyle:{{ width:2.5, type:'dashed', color:'#ffb74d' }}, itemStyle:{{ color:'#ffb74d' }} }}
          ]
        }});
        window.addEventListener('resize', () => chart.resize());
        </script>"""
        st.components.v1.html(html, height=390)
    else:
        st.line_chart(show.set_index("order_date"))

    st.caption(f"口径说明：预测数据源为 dws.dws_sales_day（有效订单），GMV 合计与 ADS 层 KPI 逐位一致；"
               f"{source_note}；模型实现见 python/gmv_forecast.py")
    return show.rename(columns={"gmv_pred": "预测GMV"})

with st.sidebar:
    st.header("💡 示例问题")
    for q in EXAMPLES:
        if st.button(q, key=f"ex_{q}", use_container_width=True):
            st.session_state.pending = q

    st.divider()
    st.header("🕘 历史对话")
    for i, (q, sql, df, err, _) in enumerate(reversed(st.session_state.history)):
        with st.expander(("❌ " if err else "✅ ") + q, expanded=False):
            if sql:
                st.code(sql, language="sql")
            if err:
                st.error(err)
            elif df is not None:
                st.dataframe(df.head(20), use_container_width=True)

    if st.session_state.history:
        if st.button("🗑️ 清空历史", use_container_width=True):
            st.session_state.history = []
            st.rerun()

# ----------------------------------------------------------------------
# 图表渲染：按结果形状自动推荐图表类型，用 ECharts（本地内联）渲染
# ----------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _echarts_js():
    """读取本地 echarts.min.js，内联进组件避免依赖外网 CDN"""
    for p in (os.path.join(_HERE, "screen", "echarts.min.js"),
              os.path.join(_HERE, "echarts.min.js")):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
    return None


def pick_chart(df: pd.DataFrame):
    cols = [c.lower() for c in df.columns]
    if len(df) == 1 and len(cols) == 1:
        return "table"
    if any("month" in c or "date" in c or "order_date" in c for c in cols) and len(df) >= 3:
        return "line"
    if len(df) >= 3 and len(df.columns) == 2 and pd.api.types.is_numeric_dtype(df[df.columns[1]]):
        return "bar"
    return "bar" if len(df) <= 15 else "table"


def render_chart(df: pd.DataFrame):
    kind = pick_chart(df)
    if kind == "table":
        st.dataframe(df, use_container_width=True)
        return

    y = pd.to_numeric(df[df.columns[1]], errors="coerce").fillna(0).tolist()
    x = df[df.columns[0]].astype(str).tolist()
    if kind == "line":
        series = (f"{{ type:'line', name:{json.dumps(df.columns[1])}, smooth:true, data:{json.dumps(y)},"
                  " lineStyle:{ width:3, color:'#00e5ff' }, itemStyle:{ color:'#00e5ff' },"
                  " areaStyle:{ color:'rgba(0,229,255,.25)' } }")
    else:
        series = (f"{{ type:'bar', name:{json.dumps(df.columns[1])}, data:{json.dumps(y)}, barMaxWidth:28,"
                  " itemStyle:{ borderRadius:6, color:new echarts.graphic.LinearGradient(0,0,0,1,"
                  "[{offset:0,color:'#00e5ff'},{offset:1,color:'#7c4dff'}]) } }")

    js = _echarts_js()
    if js:
        cid = f"c_{abs(hash(tuple(x))) % 99999}"
        html = f"""
        <div id="{cid}" style="width:100%;height:380px;"></div>
        <script>{js}</script>
        <script>
        const chart = echarts.init(document.getElementById('{cid}'), null, {{renderer:'canvas'}});
        chart.setOption({{
          backgroundColor: 'transparent',
          tooltip: {{ trigger: 'axis' }},
          grid: {{ left: 70, right: 40, top: 40, bottom: 60 }},
          xAxis: {{ type:'category', data:{json.dumps(x)},
            axisLabel:{{ color:'#7fa3d9', rotate:30, fontSize:12 }},
            axisLine:{{ lineStyle:{{ color:'#2a4a80' }} }} }},
          yAxis: {{ type:'value', axisLabel:{{ color:'#7fa3d9' }},
            splitLine:{{ lineStyle:{{ color:'rgba(42,74,128,.35)', type:'dashed' }} }} }},
          series: [{series}]
        }});
        window.addEventListener('resize', () => chart.resize());
        </script>"""
        st.components.v1.html(html, height=390)
    else:
        st.bar_chart(df.set_index(df.columns[0])[df.columns[1]])
    st.caption(f"图表类型：{kind}（依据结果形状自动推荐）")


# ----------------------------------------------------------------------
# 提问处理
# ----------------------------------------------------------------------
_pending = st.session_state.pop("pending", None)
question = _pending or st.text_input(
    "请输入你的问题，例如：广东省上月销售额是多少？", key="q_input")

# 只在「新问题」时执行：页面重跑时输入框残留的旧值不重复查询
if question and (_pending or question != st.session_state.get("_last_run_q", "")):
    st.session_state._last_run_q = question
    result = {"sql": None, "df": None, "err": None, "note": "", "forecast": False}

    # 预测类问题：不走 NL2SQL，直接读第 3 周预测产物渲染
    if is_forecast_question(question):
        result["forecast"] = True
        result["note"] = "预测问答：读取第 3 周 GMV 预测产物（python/gmv_forecast.py 产出）"
        if _forecast_dir() is None:
            result["err"] = "未找到预测结果目录 output/forecast/，请先运行 python/gmv_forecast.py"
    else:
        engine = st.session_state._nl2sql
        if engine is None:
            result["err"] = ("NL2SQL 初始化失败：" + st.session_state.get("_init_err", "未知错误")
                             + "　请确认 Hive 服务已启动（docker compose up -d）")
        else:
            try:
                with st.spinner("🤔 正在生成 SQL 并执行 …"):
                    r = engine.ask(question, show_sql=False, do_exec=True)
                result["sql"] = r.get("sql") or ""
                result["err"] = r.get("error")
                result["note"] = f"链路：{r.get('mode')}　耗时：{r.get('elapsed')}s"
                cols = r.get("columns") or []
                rows = r.get("rows") or []
                result["df"] = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame()
            except Exception as e:
                result["err"] = str(e)

    st.session_state.last_result = result
    st.session_state.history.append(
        (question, result["sql"] or ("（预测问答：读取 output/forecast 预测产物）" if result["forecast"] else ""),
         result["df"], result["err"], None))
    st.rerun()

# ----------------------------------------------------------------------
# 常驻展示最近一次问答结果（页面重跑后仍保留在主区域）
# ----------------------------------------------------------------------
_last = st.session_state.get("last_result")
if _last and st.session_state.get("_last_run_q"):
    if _last.get("note"):
        st.caption(_last["note"])
    if _last.get("forecast"):
        if _last.get("err"):
            st.error(_last["err"])
        else:
            render_forecast(st.session_state._last_run_q)
    else:
        if _last.get("sql"):
            st.markdown("**生成的 SQL：**")
            st.code(_last["sql"], language="sql")
        if _last.get("err"):
            st.error("执行出错：" + str(_last["err"]))
        elif _last.get("df") is not None:
            df = _last["df"]
            if df.empty:
                st.warning("查询成功，但没有返回数据。")
            else:
                st.markdown(f"**查询结果（{len(df)} 行）：**")
                render_chart(df)
