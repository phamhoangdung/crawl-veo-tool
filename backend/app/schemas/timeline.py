from typing import Any

from pydantic import BaseModel


class TimelineSaveRequest(BaseModel):
    tracks: list[dict[str, Any]]


class TimelineRead(BaseModel):
    tracks: list[dict[str, Any]] | None = None


class TimelineRenderRead(BaseModel):
    rendered_path: str


class WaveformRead(BaseModel):
    peaks: list[float]
