"""
第3周 子任务2：日 GMV 预测建模
================================
输入：dws.dws_sales_day（或本地 CSV 副本）
输出：未来 7 天 GMV 预测 + 模型评估指标（MAE / MAPE / RMSE）+ 图表数据

方法（三模型对比，取验证集最优）
  1. 移动平均基线（MA7）        —— 衡量"不用模型"的下限
  2. 线性回归（趋势 + 星期效应） —— 可解释，能拆出趋势与周内波动
  3. XGBoost（可选，若已安装）   —— 捕捉非线性，样本量小时易过拟合

验证方式：时间序列留出法，最后 14 天做验证集（不能随机切分，否则未来信息泄漏）

用法
  python gmv_forecast.py                       # 默认从 Hive 读取
  python gmv_forecast.py --source csv --csv data/dws_sales_day.csv
  python gmv_forecast.py --horizon 7 --outdir ../output/forecast
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


# ----------------------------------------------------------------------
# 数据读取
# ----------------------------------------------------------------------
def load_from_hive(host="localhost", port=10000, db="dws", table="dws_sales_day"):
    """通过 pyhive 读取 HiveServer2 的日汇总表"""
    try:
        from pyhive import hive
    except ImportError:
        raise RuntimeError("未安装 pyhive，请 pip install pyhive thrift 或改用 --source csv")

    conn = hive.Connection(host=host, port=port, username="hive", database=db)
    try:
        df = pd.read_sql(f"select order_date, gmv, order_cnt, user_cnt from {table}", conn)
    finally:
        conn.close()
    return df


def load_from_csv(path):
    df = pd.read_csv(path)
    return df


def prepare(df):
    """统一字段类型、补齐缺失日期、按日期排序"""
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    df["order_date"] = pd.to_datetime(df["order_date"]).dt.normalize()
    df["gmv"] = pd.to_numeric(df["gmv"], errors="coerce")
    df = df.dropna(subset=["gmv"]).sort_values("order_date")

    # 补齐无成交的日期（真实业务中会存在零成交日，缺失不补会让序列错位）
    full = pd.date_range(df["order_date"].min(), df["order_date"].max(), freq="D")
    df = df.set_index("order_date").reindex(full)
    df["gmv"] = df["gmv"].fillna(0.0)
    df.index.name = "order_date"
    return df.reset_index()


# ----------------------------------------------------------------------
# 特征工程
# ----------------------------------------------------------------------
def build_features(df):
    """t=线性趋势项；sin/cos=周内周期项（比 6 个哑变量更省参数，避免小样本过拟合）"""
    X = pd.DataFrame(index=df.index)
    X["t"] = np.arange(len(df))
    dow = df["order_date"].dt.day_of_week  # 0=周一
    X["sin_w"] = np.sin(2 * np.pi * dow / 7)
    X["cos_w"] = np.cos(2 * np.pi * dow / 7)
    X["is_weekend"] = (dow >= 5).astype(int)
    return X


def fit_ols(X, y):
    """最小二乘闭式解（带截距），返回系数向量"""
    A = np.column_stack([np.ones(len(X)), X.values])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    return coef


def predict_ols(coef, X):
    A = np.column_stack([np.ones(len(X)), X.values])
    return A @ coef


# ----------------------------------------------------------------------
# 评估
# ----------------------------------------------------------------------
def metrics(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mask = np.abs(y_true) > 1e-9
    mape = float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100) if mask.any() else float("nan")
    return {"MAE": round(mae, 2), "RMSE": round(rmse, 2), "MAPE(%)": round(mape, 2)}


def validate(df, val_days=14):
    """时间序列留出验证：前 N-14 天训练，最后 14 天验证"""
    n = len(df)
    if n <= val_days + 14:
        val_days = max(7, n // 5)

    train, val = df.iloc[:-val_days], df.iloc[-val_days:]
    X_all = build_features(df)
    X_tr, X_va = X_all.iloc[:-val_days], X_all.iloc[-val_days:]
    y_tr, y_va = train["gmv"].values, val["gmv"].values

    results = {}

    # 1) 移动平均基线（用训练集最后 7 天的均值做常数预测）
    ma_pred = np.full(len(y_va), train["gmv"].tail(7).mean())
    results["MA7基线"] = {"pred": ma_pred, **metrics(y_va, ma_pred)}

    # 2) 线性回归
    coef = fit_ols(X_tr, y_tr)
    lr_pred = predict_ols(coef, X_va)
    results["线性回归"] = {"pred": lr_pred, **metrics(y_va, lr_pred)}

    # 3) XGBoost（可选）
    try:
        import xgboost as xgb  # noqa: F401
        model = xgb.XGBRegressor(
            n_estimators=200, max_depth=3, learning_rate=0.05,
            subsample=0.9, colsample_bytree=0.9, random_state=42, objective="reg:squarederror",
        )
        model.fit(X_tr.values, y_tr)
        xgb_pred = model.predict(X_va.values)
        results["XGBoost"] = {"pred": xgb_pred, **metrics(y_va, xgb_pred)}
    except Exception:
        pass

    best = min(results.items(), key=lambda kv: kv[1]["MAE"])
    return results, best[0], train, val, coef


# ----------------------------------------------------------------------
# 预测
# ----------------------------------------------------------------------
def forecast(df, horizon=7, model="线性回归"):
    """用全量数据重训后外推 horizon 天"""
    X_all = build_features(df)
    y = df["gmv"].values

    if model == "MA7基线":
        last = pd.to_datetime(df["order_date"].max())
        dates = [last + timedelta(days=i) for i in range(1, horizon + 1)]
        level = df["gmv"].tail(7).mean()
        return pd.DataFrame({"order_date": dates, "gmv_pred": [round(level, 2)] * horizon})

    coef = fit_ols(X_all, y)
    last = pd.to_datetime(df["order_date"].max())
    future = pd.DataFrame({"order_date": [last + timedelta(days=i) for i in range(1, horizon + 1)]})
    future["t"] = np.arange(len(df), len(df) + horizon)
    dow = future["order_date"].dt.day_of_week
    future["sin_w"] = np.sin(2 * np.pi * dow / 7)
    future["cos_w"] = np.cos(2 * np.pi * dow / 7)
    future["is_weekend"] = (dow >= 5).astype(int)
    pred = predict_ols(coef, future[["t", "sin_w", "cos_w", "is_weekend"]])
    future["gmv_pred"] = np.round(np.maximum(pred, 0), 2)
    return future[["order_date", "gmv_pred"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["hive", "csv"], default="hive")
    ap.add_argument("--csv", default=os.path.join(HERE, "data", "dws_sales_day.csv"))
    ap.add_argument("--host", default=os.environ.get("HIVE_HOST", "localhost"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("HIVE_PORT", 10000)))
    ap.add_argument("--horizon", type=int, default=7)
    ap.add_argument("--outdir", default=os.path.join(HERE, "..", "output", "forecast"))
    args = ap.parse_args()

    # 读取
    if args.source == "csv":
        df = load_from_csv(args.csv)
        src = args.csv
    else:
        try:
            df = load_from_hive(host=args.host, port=args.port)
            src = "hive:dws.dws_sales_day"
        except Exception as e:
            print(f"[WARN] Hive 读取失败({e})，回退到 CSV: {args.csv}")
            df = load_from_csv(args.csv)
            src = args.csv

    df = prepare(df)
    print(f"数据源 {src} | 样本 {len(df)} 天 | {df['order_date'].min().date()} ~ {df['order_date'].max().date()}")
    print(f"GMV 合计 {df['gmv'].sum():,.2f} 元，日均 {df['gmv'].mean():,.2f} 元")

    # 验证
    results, best_name, train, val, _ = validate(df)
    print("\n=== 验证集评估（最后 %d 天）===" % len(val))
    for name, r in results.items():
        print(f"{name:<10} MAE={r['MAE']:>12,.2f}  RMSE={r['RMSE']:>12,.2f}  MAPE={r['MAPE(%)']:>6.2f}%")
    print(f"最优模型：{best_name}（按 MAE）")

    # 预测
    fc = forecast(df, horizon=args.horizon, model=best_name)
    print(f"\n=== 未来 {args.horizon} 天预测（{best_name}）===")
    for _, r in fc.iterrows():
        print(f"{r['order_date'].date()}  {r['gmv_pred']:>14,.2f} 元")

    # 落盘
    os.makedirs(args.outdir, exist_ok=True)
    fc.to_csv(os.path.join(args.outdir, "forecast_7d.csv"), index=False, encoding="utf-8-sig")
    df.to_csv(os.path.join(args.outdir, "series_history.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame({
        "order_date": val["order_date"].dt.date,
        "actual": val["gmv"].values,
        "pred": results[best_name]["pred"],
    }).to_csv(os.path.join(args.outdir, "validation_actual.csv"), index=False, encoding="utf-8-sig")

    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": src,
        "sample_days": int(len(df)),
        "date_range": [str(df["order_date"].min().date()), str(df["order_date"].max().date())],
        "total_gmv": round(float(df["gmv"].sum()), 2),
        "avg_daily_gmv": round(float(df["gmv"].mean()), 2),
        "validation_days": int(len(val)),
        "metrics": {k: {kk: vv for kk, vv in v.items() if kk != "pred"} for k, v in results.items()},
        "best_model": best_name,
        "forecast_7d": [
            {"date": str(r["order_date"].date()), "gmv_pred": float(r["gmv_pred"])} for _, r in fc.iterrows()
        ],
        "forecast_total": round(float(fc["gmv_pred"].sum()), 2),
    }
    with open(os.path.join(args.outdir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n结果已写入 {os.path.abspath(args.outdir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
