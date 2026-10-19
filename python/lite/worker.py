"""Run blocking AKShare calls in disposable processes with a hard time budget."""

import contextlib
import datetime as dt
import json
import sys

import akshare as ak

from lite.metrics import METRICS


def fetch(kind: str, symbol: str) -> str:
    """Use the same free AKShare ecosystem as the upstream asset adapter."""
    code = symbol[2:]
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    if kind == "history":
        frame = ak.stock_zh_a_hist_tx(
            symbol=symbol,
            start_date=(today - dt.timedelta(days=180)).strftime("%Y%m%d"),
            end_date=today.strftime("%Y%m%d"),
            adjust="qfq",
            timeout=12,
        ).tail(90)
    elif kind == "financials":
        frame = ak.stock_financial_abstract_new_ths(symbol=code, indicator="按报告期")
        # Keep a coherent latest report rather than mixing reporting periods.
        frame = frame.sort_values("report_date", ascending=False)
        frame = frame[frame["report_date"] == frame.iloc[0]["report_date"]].head(30)
        frame["metric_label"] = frame["metric_name"].map(
            lambda key: METRICS.get(key, (key, "源站口径"))[0]
        )
        frame["unit"] = frame["metric_name"].map(
            lambda key: METRICS.get(key, (key, "源站口径"))[1]
        )
        order = {key: i for i, key in enumerate(METRICS)}
        frame = frame.sort_values("metric_name", key=lambda col: col.map(order).fillna(100))
    elif kind == "news":
        frame = ak.stock_news_em(symbol=code).sort_values("发布时间", ascending=False).head(8)
    else:
        raise ValueError("Unsupported dataset")
    return frame.to_json(orient="records", force_ascii=False, date_format="iso")


if __name__ == "__main__":
    try:
        # Progress bars and upstream prints must not corrupt the JSON protocol.
        with contextlib.redirect_stdout(sys.stderr):
            payload = fetch(sys.argv[1], sys.argv[2])
        print(payload)
    except Exception as exc:
        # This process boundary contains third-party provider failures.
        print(json.dumps({"error": type(exc).__name__}))
        sys.exit(1)
