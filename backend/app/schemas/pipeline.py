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
    burned_path: str | None = None
    # Thông tin hiển thị ở trang chi tiết; optional để các endpoint pipeline
    # (chỉ trả trạng thái sau khi kích hoạt) không phải nạp đủ.
    title: str | None = None
    author_name: str | None = None
    cover_url: str | None = None
    source_url: str | None = None
    duration_seconds: int | None = None
    local_path: str | None = None
    error_message: str | None = None
