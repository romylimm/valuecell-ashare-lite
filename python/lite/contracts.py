"""Small contracts shared by the data and research layers."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    symbol: str = Field(min_length=6, max_length=16)
    use_ai: bool = False


class Dataset(BaseModel):
    status: Literal["ok", "unavailable"]
    source: str
    url: str
    fetched_at: str
    data: list[dict[str, Any]] = Field(default_factory=list)
    message: str = ""


class AnalysisReport(BaseModel):
    symbol: str
    generated_at: str
    datasets: dict[str, Dataset]
    observations: list[str]
    warnings: list[str]
    ai_status: str = "未启用"
    ai_text: str = ""
    cached: bool = False
