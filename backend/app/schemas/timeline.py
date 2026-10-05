from typing import Any

from pydantic import BaseModel


class TimelineSaveRequest(BaseModel):
    tracks: list[dict[str, Any]]


class TimelineRead(BaseModel):
    tracks: list[dict[str, Any]] | None = None


class TimelineRenderRead(BaseModel):
    rendered_path: str


class AudioStemsRead(BaseModel):
    """Separated audio tracks — None means the dubbing step has not run."""

    voice: str | None = None
    background: str | None = None
    mixed: str | None = None


class WaveformRead(BaseModel):
    peaks: list[float]
