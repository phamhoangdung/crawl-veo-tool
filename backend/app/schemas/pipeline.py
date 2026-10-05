from pydantic import BaseModel


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    translated_text: str = ""
    # Phase 19: speaker label (e.g. "SPEAKER_00") — empty means speaker separation has not
    # run, and the video is still dubbed normally with the shared default voice.
    speaker: str = ""


class TranslateRequest(BaseModel):
    source_lang: str = "zh"
    target_lang: str = "vi"


class VoiceRef(BaseModel):
    """Reference to one specific voice — enough info for tts_service to know which
    provider to call with which voice id (Edge-TTS has no notion of an 'account' like
    ElevenLabs, so the `provider` field name of ApiKey is not reused directly)."""

    provider: str  # "edge" | "elevenlabs"
    voice_id: str


class VoiceOption(BaseModel):
    """1 option shown in the voice picker list in the UI (Phase 19)."""

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
    # Phase 19: map speaker_label -> assigned voice; a speaker not assigned has no key.
    speaker_voices: dict[str, VoiceRef] = {}
    # Info shown on the detail page; optional so pipeline endpoints
    # (which only return state after being triggered) do not have to load everything.
    title: str | None = None
    author_name: str | None = None
    cover_url: str | None = None
    source_url: str | None = None
    duration_seconds: int | None = None
    local_path: str | None = None
    error_message: str | None = None
