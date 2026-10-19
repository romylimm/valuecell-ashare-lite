"""Regression checks for truthful partial reports and the lightweight API."""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

import lite.app as api
from lite.contracts import Dataset
from lite.data import ak_dataset, normalize_symbol, parse_quote
from lite.research import explain, summarize


def evidence() -> dict[str, Dataset]:
    result = {
        key: Dataset(status="unavailable", source="test", url="https://example.com",
                     fetched_at="2026-10-19T10:00:00+08:00", message="source offline")
        for key in ("quote", "history", "financials", "news")
    }
    result["history"].status = "ok"
    result["history"].data = [{"date": f"2026-09-{i:02}", "close": float(i)} for i in range(1, 22)]
    return result


@pytest.mark.parametrize(("raw", "expected"), [
    ("600519", "sh600519"), ("000001.SZ", "sz000001"),
    (" SH600519 ", "sh600519"), ("920001", "bj920001"),
])
def test_normalize(raw: str, expected: str) -> None:
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize("raw", ["sh000001", "600519.SZ", "sh600519.sz", "510300", "AAPL", "../600519"])
def test_reject_wrong_market_and_injection(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_symbol(raw)


def test_quote_mapping_and_missing() -> None:
    fields = [""] * 50
    for index, value in {1: "贵州茅台", 2: "600519", 3: "1500", 4: "1490",
                         30: "20261019150000", 32: "0.67", 39: "20", 45: "19000", 46: "8"}.items():
        fields[index] = value
    row = parse_quote('v_sh600519="' + "~".join(fields) + '";', "sh600519")
    assert row["name"] == "贵州茅台"
    assert row["pe_ttm"] == 20
    with pytest.raises(ValueError):
        parse_quote('v_pv_none_match="1";', "sh600519")


def test_calculation_and_partial_failure() -> None:
    report = summarize("sh600519", evidence())
    assert any("11.50" in line for line in report.observations)
    assert any("+2000.00%" in line for line in report.observations)
    assert any("财务缺失" in line for line in report.warnings)
    assert not report.datasets["financials"].data


def test_financial_report_period_and_zero_value() -> None:
    datasets = evidence()
    datasets["financials"].status = "ok"
    datasets["financials"].data = [{
        "metric_name": "calculate_operating_income_total_yoy_growth_ratio",
        "value": "0", "report_date": "2026-06-30",
    }]
    report = summarize("sh600519", datasets)
    assert any("2026-06-30" in line and "0.00%" in line for line in report.observations)


@pytest.mark.asyncio
async def test_model_missing_retains_report(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LITE_LLM_BASE_URL", raising=False)
    report = summarize("sh600519", evidence())
    await explain(report)
    assert "未配置" in report.ai_status
    assert report.observations


@pytest.mark.asyncio
async def test_provider_timeout_kills_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    class Process:
        returncode = None

        async def communicate(self) -> tuple[bytes, bytes]:
            if self.returncode is None:
                await asyncio.sleep(10)
            return b"[]", b""

        def kill(self) -> None:
            self.returncode = -1

    process = Process()
    monkeypatch.setattr("lite.data.DATA_TIMEOUT", 0.01)
    monkeypatch.setattr("lite.data.asyncio.create_subprocess_exec", AsyncMock(return_value=process))
    result = await ak_dataset("news", "sh600519")
    assert result.status == "unavailable"
    assert process.returncode == -1


@pytest.mark.asyncio
async def test_api_validation_cache_and_static(monkeypatch: pytest.MonkeyPatch) -> None:
    api.cache.clear()
    provider = AsyncMock(return_value=evidence())
    monkeypatch.setattr(api, "collect", provider)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
        invalid = await client.post("/api/analyze", json={"symbol": "sh000001"})
        assert invalid.status_code == 422
        first = await client.post("/api/analyze", json={"symbol": "600519"})
        assert first.status_code == 200
        assert not first.json()["cached"]
        second = await client.post("/api/analyze", json={"symbol": "SH600519"})
        assert second.json()["cached"]
        assert provider.await_count == 1
        assert "股票代码" in (await client.get("/")).text
        assert (await client.get("/static/app.js")).status_code == 200


@pytest.mark.asyncio
async def test_total_outage_does_not_cache_or_invent(monkeypatch: pytest.MonkeyPatch) -> None:
    api.cache.clear()
    datasets = evidence()
    for dataset in datasets.values():
        dataset.status = "unavailable"
        dataset.data = []
    monkeypatch.setattr(api, "collect", AsyncMock(return_value=datasets))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
        response = await client.post("/api/analyze", json={"symbol": "600519"})
    assert response.status_code == 200
    assert "无法生成" in response.json()["observations"][0]
    assert not api.cache


@pytest.mark.asyncio
async def test_model_error_preserves_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITE_LLM_BASE_URL", "https://model.example/v1")
    monkeypatch.setenv("LITE_LLM_MODEL", "test")
    monkeypatch.setattr(httpx.AsyncClient, "post", AsyncMock(side_effect=httpx.ConnectError("offline")))
    report = summarize("sh600519", evidence())
    await explain(report)
    assert "暂不可用" in report.ai_status
    assert report.datasets["history"].data
