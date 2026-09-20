from pydantic import BaseModel


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    translated_text: str = ""
    # Phase 19: nhãn người nói (vd "SPEAKER_00") — rỗng nghĩa là chưa chạy phân
    # vai, video vẫn lồng tiếng bình thường bằng giọng mặc định chung.
    speaker: str = ""


class TranslateRequest(BaseModel):
    source_lang: str = "zh"
    target_lang: str = "vi"


class VoiceRef(BaseModel):
    """Tham chiếu 1 giọng đọc cụ thể — đủ thông tin để tts_service biết gọi
    provider nào với voice id nào (Edge-TTS không có khái niệm 'tài khoản' như
    ElevenLabs, nên không tái dùng thẳng tên field `provider` của ApiKey)."""

    provider: str  # "edge" | "elevenlabs"
    voice_id: str


class VoiceOption(BaseModel):
    """1 lựa chọn hiện trong danh sách chọn giọng ở UI (Phase 19)."""

    provider: str
    voice_id: str
    name: str
    gender: str = "unknown"


class VideoDetailRead(BaseModel):
    id: int
    status: str
    transcript: list[TranscriptSegment]
    dubbed_path: str | None
    burned_path: str | None = None
    # Phase 19: map speaker_label -> giọng đã gán, vai chưa gán thì không có key.
    speaker_voices: dict[str, VoiceRef] = {}
    # Thông tin hiển thị ở trang chi tiết; optional để các endpoint pipeline
    # (chỉ trả trạng thái sau khi kích hoạt) không phải nạp đủ.
    title: str | None = None
    author_name: str | None = None
    cover_url: str | None = None
    source_url: str | None = None
    duration_seconds: int | None = None
    local_path: str | None = None
    error_message: str | None = None
