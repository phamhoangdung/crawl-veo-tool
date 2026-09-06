from pydantic import BaseModel


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    translated_text: str = ""


class TranslateRequest(BaseModel):
    source_lang: str = "zh"
    target_lang: str = "vi"


class VideoDetailRead(BaseModel):
    id: int
    status: str
    transcript: list[TranscriptSegment]
    dubbed_path: str | None
