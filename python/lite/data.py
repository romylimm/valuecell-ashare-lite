"""Free A-share sources, validation and bounded asynchronous data collection."""

import asyncio
import datetime as dt
import json
import math
import os
import re
import sys
from pathlib import Path

import httpx
from loguru import logger

from lite.contracts import Dataset

TIMEZONE = dt.timezone(dt.timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
DATA_TIMEOUT = 30


def now() -> str:
    return dt.datetime.now(TIMEZONE).isoformat(timespec="seconds")


def normalize_symbol(value: str) -> str:
    """Accept explicit exchanges but reject indices, funds and mismatched prefixes."""
    value = value.strip().lower()
    match = re.fullmatch(r"(?:(sh|sz|bj))?(\d{6})(?:\.(sh|sz|bj))?", value)
    if not match:
        raise ValueError("请输入六位 A 股代码，例如 600519 或 000001。")
    prefix, code, suffix = match.groups()
    if code.startswith(("600", "601", "603", "605", "688", "689")):
        exchange = "sh"
    elif code.startswith(("000", "001", "002", "003", "300", "301")):
        exchange = "sz"
    elif code.startswith(("4", "8", "92")):
        exchange = "bj"
    else:
        raise ValueError("当前只支持沪深北 A 股，不支持指数、基金或港美股。")
    if any(item is not None and item != exchange for item in (prefix, suffix)):
        raise ValueError("交易所与股票代码不匹配。")
    return exchange + code


def number(value: object) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def parse_quote(text: str, symbol: str) -> dict:
    """Tencent uses a GBK, tilde-delimited quote format."""
    match = re.search(r'="([^"\r\n]*)"', text)
    fields = match.group(1).split("~") if match else []
    if len(fields) < 47 or fields[2] != symbol[2:]:
        raise ValueError("未找到该股票的有效行情")
    price = number(fields[3])
    if price is None or price <= 0:
        raise ValueError("该股票暂无有效价格")
    return {
        "name": fields[1], "code": fields[2], "price": price,
        "previous_close": number(fields[4]), "change_percent": number(fields[32]),
        "quote_time": fields[30], "pe_ttm": number(fields[39]),
        "pb": number(fields[46]), "market_cap_yi": number(fields[45]),
        "currency": "CNY",
    }


async def quote(symbol: str) -> Dataset:
    url = f"https://qt.gtimg.cn/q={symbol}"
    result = Dataset(status="unavailable", source="腾讯证券", url=url, fetched_at=now())
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(url)
            response.raise_for_status()
        result.data = [parse_quote(response.content.decode("gbk", errors="replace"), symbol)]
        result.status = "ok"
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Quote unavailable for {}: {}", symbol, type(exc).__name__)
        result.message = "行情源暂不可用，或代码不存在。请稍后重试。"
    return result


async def ak_dataset(kind: str, symbol: str) -> Dataset:
    sources = {
        "history": ("腾讯证券 / AKShare（前复权日线）", f"https://gu.qq.com/{symbol}/gp"),
        "financials": ("同花顺 / AKShare", f"https://basic.10jqka.com.cn/new/{symbol[2:]}/finance.html"),
        "news": ("东方财富 / AKShare", f"https://so.eastmoney.com/news/s?keyword={symbol[2:]}"),
    }
    source, url = sources[kind]
    result = Dataset(status="unavailable", source=source, url=url, fetched_at=now())
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "lite.worker", kind, symbol,
        cwd=ROOT, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=DATA_TIMEOUT)
        payload = json.loads(stdout.decode("utf-8"))
        if process.returncode != 0 or not isinstance(payload, list):
            raise ValueError("Provider failed")
        if not payload:
            raise ValueError("Empty dataset")
        result.status = "ok"
        result.data = payload
    except (TimeoutError, ValueError, UnicodeError) as exc:
        logger.warning("Dataset {} unavailable for {}: {}", kind, symbol, type(exc).__name__)
        result.message = "数据源未返回有效数据（可能限流、超时或暂无记录），本次分析将跳过。"
    finally:
        if process.returncode is None:
            process.kill()
            await process.communicate()
    return result


async def collect(symbol: str) -> dict[str, Dataset]:
    names = ("quote", "history", "financials", "news")
    values = await asyncio.gather(quote(symbol), *(ak_dataset(k, symbol) for k in names[1:]))
    return dict(zip(names, values, strict=True))
