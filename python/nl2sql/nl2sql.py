"""
NL2SQL 主链路：自然语言 -> SQL -> Hive 执行 -> 结果表
=====================================================
链路组成（对应任务书子任务 3~4）
  1. Schema 抽取（schema_extractor）  —— 把库表结构 + 业务口径注入 Prompt
  2. Prompt 组装（prompts）           —— 系统规则 + 5 个 few-shot 示例
  3. LLM 生成（LangChain ChatOpenAI） —— 兼容 DeepSeek / 通义千问等 OpenAI 协议服务
  4. SQL 校验（guard）                —— 只放行 SELECT，自动补 limit，屏蔽 DDL/DML
  5. 执行（pyhive）                   —— 返回列名 + 数据行，供上层渲染

三种运行模式
  · llm      ：有 API Key，走大模型（正式演示）
  · offline  ：无 Key，走规则兜底（保证无网络也能演示闭环）

用法
  python nl2sql.py "2024年7月的GMV是多少"
  python nl2sql.py "各渠道销售额占比" --show-sql
  python nl2sql.py "复购率" --offline
"""

import argparse
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from schema_extractor import build_schema_text, load_schema  # noqa: E402
from prompts import SYSTEM_PROMPT, build_user_prompt, fallback_sql  # noqa: E402


# ----------------------------------------------------------------------
# 环境配置
# ----------------------------------------------------------------------
def load_env():
    try:
        from dotenv import load_dotenv
        for p in (os.path.join(HERE, ".env"), os.path.join(HERE, "..", ".env")):
            if os.path.exists(p):
                load_dotenv(p)
                break
    except ImportError:
        pass


def hive_conf():
    return dict(
        host=os.environ.get("HIVE_HOST", "localhost"),
        port=int(os.environ.get("HIVE_PORT", 10000)),
        user=os.environ.get("HIVE_USER", "hive"),
        database=os.environ.get("HIVE_DB", "dws"),
    )


# ----------------------------------------------------------------------
# LLM 客户端：优先 LangChain，退化为 openai SDK
# ----------------------------------------------------------------------
class LLMClient:
    def __init__(self):
        self.api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
        self.model = os.environ.get("LLM_MODEL", "deepseek-chat")
        self.backend = None
        self.client = None
        if not self.api_key:
            return
        try:
            from langchain_openai import ChatOpenAI
            self.client = ChatOpenAI(model=self.model, api_key=self.api_key,
                                     base_url=self.base_url, temperature=0, timeout=60)
            self.backend = "langchain"
        except ImportError:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=60)
                self.backend = "openai-sdk"
            except ImportError:
                self.backend = None

    @property
    def available(self):
        return self.backend is not None

    def complete(self, system, user):
        if self.backend == "langchain":
            from langchain_core.messages import HumanMessage, SystemMessage
            resp = self.client.invoke([SystemMessage(content=system), HumanMessage(content=user)])
            return resp.content
        if self.backend == "openai-sdk":
            resp = self.client.chat.completions.create(
                model=self.model, temperature=0,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
            )
            return resp.choices[0].message.content
        raise RuntimeError("未配置大模型（缺少 LLM_API_KEY）")


# ----------------------------------------------------------------------
# SQL 解析与安全校验
# ----------------------------------------------------------------------
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|msck|load\s+data|overwrite)\b",
    re.IGNORECASE,
)


def extract_sql(text):
    """从模型输出里抠出 SQL：优先取 ```sql 代码块，否则取第一个 select/with 到最后"""
    if not text:
        return ""
    m = re.search(r"```(?:sql)?\s*(.+?)```", text, re.S | re.I)
    if m:
        return m.group(1).strip().rstrip(";")
    m = re.search(r"(?is)\b(select|with)\b.*", text)
    return (m.group(0).strip().rstrip(";") if m else "")


def guard(sql, max_rows=200):
    """安全闸门：非查询语句直接拒绝；无 limit 的查询补 limit，避免误拉全表"""
    if not sql:
        raise ValueError("未解析到 SQL")
    one_line = sql.strip()
    if not re.match(r"(?is)^\s*(select|with)\b", one_line):
        raise ValueError(f"仅允许查询语句，实际为：{one_line[:40]}...")
    bad = FORBIDDEN.search(one_line)
    if bad:
        raise ValueError(f"检测到非法关键字：{bad.group(0)}")
    if " limit " not in one_line.lower():
        one_line = one_line + f"\nlimit {max_rows}"
    return one_line


def execute(sql, limit_note=True):
    """执行 SQL，返回 (列名, 行列表)"""
    from pyhive import hive
    conf = hive_conf()
    conn = hive.Connection(host=conf["host"], port=conf["port"],
                           username=conf["user"], database=conf["database"])
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0].split(".")[-1] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        return cols, rows
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
class NL2SQL:
    def __init__(self, refresh_schema=False, offline=False, max_rows=200):
        load_env()
        self.max_rows = int(os.environ.get("MAX_ROWS", max_rows))
        self.schema, self.schema_source = load_schema(refresh=refresh_schema, **{
            k: v for k, v in hive_conf().items() if k in ("host", "port")
        })
        self.schema_text = build_schema_text(self.schema)
        self.llm = None if offline else LLMClient()
        self.mode = "offline" if (offline or not self.llm or not self.llm.available) else f"llm:{self.llm.model}"

    def generate(self, question):
        """返回 (sql, 说明)"""
        if self.mode.startswith("llm"):
            user = build_user_prompt(question, self.schema_text)
            raw = self.llm.complete(SYSTEM_PROMPT, user)
            return extract_sql(raw), f"由 {self.llm.model} 生成"
        sql = fallback_sql(question)
        if not sql:
            raise RuntimeError("离线模式下未命中规则库，请配置 LLM_API_KEY 或换一种问法")
        return sql, "离线规则兜底（未调用大模型）"

    def ask(self, question, show_sql=True, do_exec=True):
        t0 = time.time()
        result = {"question": question, "mode": self.mode, "sql": None, "error": None,
                  "columns": [], "rows": [], "elapsed": 0}
        try:
            sql, note = self.generate(question)
            sql = guard(sql, self.max_rows)
            result["sql"] = sql
            result["note"] = note
            if do_exec:
                result["columns"], result["rows"] = execute(sql)
        except Exception as e:
            result["error"] = str(e)
        result["elapsed"] = round(time.time() - t0, 2)
        return result


def print_result(r):
    print(f"\n问：{r['question']}")
    print(f"模式：{r['mode']} | 耗时 {r['elapsed']}s")
    if r["sql"]:
        print("SQL：")
        for line in r["sql"].splitlines():
            print("   " + line)
    if r["error"]:
        print(f"错误：{r['error']}")
        return
    if not r["columns"]:
        return
    print("结果：")
    print("   " + " | ".join(map(str, r["columns"])))
    for row in r["rows"][:20]:
        print("   " + " | ".join("" if v is None else str(v) for v in row))
    if len(r["rows"]) > 20:
        print(f"   ... 共 {len(r['rows'])} 行")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", help="自然语言问题")
    ap.add_argument("--offline", action="store_true", help="不调用大模型，用规则兜底")
    ap.add_argument("--show-sql", action="store_true", help="打印生成的 SQL")
    ap.add_argument("--no-exec", action="store_true", help="只生成 SQL，不连 Hive 执行")
    ap.add_argument("--refresh-schema", action="store_true")
    a = ap.parse_args()

    q = a.question
    if not q:
        q = input("请输入问题：").strip()

    engine = NL2SQL(refresh_schema=a.refresh_schema, offline=a.offline)
    r = engine.ask(q, do_exec=not a.no_exec)
    print_result(r)


if __name__ == "__main__":
    main()
