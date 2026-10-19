"""Standalone ValueCell Lite entry point without trading or vector DB startup."""

import asyncio
import time
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from lite.contracts import AnalysisReport, AnalysisRequest
from lite.data import collect, normalize_symbol
from lite.research import explain, model_ready, summarize

app = FastAPI(title="ValueCell Lite · A 股分析", docs_url="/api/docs")
STATIC = Path(__file__).parent / "static"
CACHE_TTL = 300
CACHE_LIMIT = 100
cache: OrderedDict[str, tuple[float, AnalysisReport]] = OrderedDict()
gate = asyncio.Semaphore(2)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "mode": "a-share-lite", "model_configured": model_ready()}


@app.post("/api/analyze", response_model=AnalysisReport)
async def analyze(request: AnalysisRequest) -> AnalysisReport:
    try:
        symbol = normalize_symbol(request.symbol)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if gate.locked():
        raise HTTPException(status_code=429, detail="正在分析其他股票，请稍后重试。")
    async with gate:
        existing = cache.get(symbol)
        if existing is not None and time.monotonic() - existing[0] < CACHE_TTL:
            report = existing[1].model_copy(deep=True)
            report.cached = True
        else:
            report = summarize(symbol, await collect(symbol))
            if any(item.status == "ok" for item in report.datasets.values()):
                cache[symbol] = (time.monotonic(), report.model_copy(deep=True))
                while len(cache) > CACHE_LIMIT:
                    cache.popitem(last=False)
        if request.use_ai:
            await explain(report)
        return report


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
