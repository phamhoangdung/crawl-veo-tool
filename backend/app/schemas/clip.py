from pydantic import BaseModel


class ClipCandidateRead(BaseModel):
    start: float
    end: float
    text: str
    score: float


class CropBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class ClipCreateRequest(BaseModel):
    start: float
    end: float
    crop: CropBox | None = None
    cta_text: str | None = None


class ClipRead(BaseModel):
    output_path: str
