# -*- coding: utf-8 -*-
"""云购生活 · 智能经营问答（Streamlit）
接入第 3 周 NL2SQL 后端，实现闭环：
  提问 → 生成 SQL（LLM / 规则兜底）→ 安全校验 → Hive 执行 → 结果展示 → ECharts 图表渲染
交互增强：历史对话侧栏、加载状态（spinner）、错误提示、示例问题、自动图表推荐
运行：streamlit run streamlit_app.py --server.port=8501
"""
import json
import os
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
if "_nl2sql" not in st.session_state:
    try:
        st.session_state._nl2sql = NL2SQL(offline=True) if NL2SQL else None
    except Exception as e:  # Hive 未启动时也能进界面
        st.session_state._nl2sql = None
        st.session_state._init_err = str(e)

EXAMPLES = [
    "2024年7月的GMV是多少",
    "各渠道销售额占比",
    "销售额最高的10个品类",
    "月度复购率",
    "各区域销售额排名",
]

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
        html = f"""
        <div id="c_{abs(hash(tuple(x))) % 99999}" style="width:100%;height:380px;"></div>
        <script>{js}</script>
        <script>
        const chart = echarts.init(document.currentScript.previousElementSibling, null, {{renderer:'canvas'}});
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
question = st.session_state.pop("pending", None) or st.text_input(
    "请输入你的问题，例如：广东省上月销售额是多少？", key="q_input")

if question:
    engine = st.session_state._nl2sql
    if engine is None:
        st.error("NL2SQL 初始化失败：" + st.session_state.get("_init_err", "未知错误")
                 + "　请确认 Hive 服务已启动（docker compose up -d）")
    else:
        sql, df, err, mode_note = None, None, None, ""
        try:
            with st.spinner("🤔 正在生成 SQL 并执行 …"):
                r = engine.ask(question, show_sql=False, do_exec=True)
            sql = r.get("sql") or ""
            err = r.get("error")
            mode_note = f"链路：{r.get('mode')}　耗时：{r.get('elapsed')}s"
            cols = r.get("columns") or []
            rows = r.get("rows") or []
            df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame()
        except Exception as e:
            err = str(e)

        if mode_note:
            st.caption(mode_note)
        if sql:
            st.markdown("**生成的 SQL：**")
            st.code(sql, language="sql")
        if err:
            st.error("执行出错：" + str(err))
        elif df is not None:
            if df.empty:
                st.warning("查询成功，但没有返回数据。")
            else:
                st.markdown(f"**查询结果（{len(df)} 行）：**")
                render_chart(df)
        st.session_state.history.append((question, sql, df, err, None))
        st.rerun()
