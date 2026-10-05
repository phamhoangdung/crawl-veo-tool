"""Generate the title / description / tags for a video before publishing.

SEO rules come from the `youtube-seo` skill (.claude/skills/youtube-seo): title under
60 characters with the main keyword in the first 5–55 characters, the 2–3 opening description sentences containing the keyword
naturally, tags are only auxiliary (title + description matter more).

The prompt can be passed in from outside so n8n can use its own script for each kind of video —
each topic (cooking, vlog, news) needs a different writing style.
"""

import json
import logging
import re

from sqlalchemy.orm import Session

from app.models.video import Video
from app.services import translate_service

logger = logging.getLogger(__name__)

MAX_TITLE_LENGTH = 60
MAX_DESCRIPTION_LENGTH = 5000
MAX_TAGS = 15

# Make the model follow real SEO rules instead of writing whimsically. `{transcript}` and
# `{title}` are replaced with the video content.
DEFAULT_PROMPT = """Bạn là chuyên gia SEO YouTube cho kênh tiếng Việt.

Video gốc (tiếng Trung): {title}
Nội dung lời thoại đã dịch:
{transcript}

Viết metadata tiếng Việt theo đúng quy tắc:
- Tiêu đề: DƯỚI 60 ký tự, từ khoá chính nằm trong 5-55 ký tự đầu, giọng tự nhiên,
  không viết HOA toàn bộ, không nhồi từ khoá.
- Mô tả: 2-3 câu đầu chứa từ khoá chính và phụ một cách tự nhiên (dưới 160 ký tự
  cho phần đầu), sau đó tóm tắt nội dung. Viết như người thật, không sáo rỗng.
- Tag: tối đa 15 tag tiếng Việt liên quan thật tới nội dung.

Trả về ĐÚNG JSON, không thêm chữ nào khác:
{{"title": "...", "description": "...", "tags": ["...", "..."]}}"""


class MetadataGenerationError(RuntimeError):
    pass


def _transcript_excerpt(video: Video, max_chars: int = 2000) -> str:
    """Take the translated dialogue as context. Truncated because a long video may exceed
    the model's token limit."""
    segments = video.transcript_json or []
    lines = [
        (s.get("translated_text") or s.get("text") or "").strip()
        for s in segments
        if (s.get("translated_text") or s.get("text") or "").strip()
    ]
    text = " ".join(lines)
    return text[:max_chars] if len(text) > max_chars else text


def _extract_json(raw: str) -> dict:
    """The model often wraps JSON in ```json ... ``` or adds an intro — strip it out."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1)
    else:
        braces = re.search(r"\{.*\}", raw, re.DOTALL)
        if braces:
            raw = braces.group(0)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MetadataGenerationError(f"Model không trả JSON hợp lệ: {raw[:200]}") from exc


def _clean(data: dict) -> dict:
    """Cut to the exact limit instead of rejecting — slightly long metadata is still usable."""
    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    raw_tags = data.get("tags") or []

    tags = [str(t).strip() for t in raw_tags if str(t).strip()][:MAX_TAGS]

    return {
        "title": title[:MAX_TITLE_LENGTH],
        "description": description[:MAX_DESCRIPTION_LENGTH],
        "tags": tags,
        # Report it so the user knows it was cut, rather than silently losing text.
        "title_truncated": len(title) > MAX_TITLE_LENGTH,
    }


async def generate_metadata(
    db: Session,
    user_id: int,
    video: Video,
    prompt_template: str | None = None,
) -> dict:
    """Generate metadata with the configured LLM. The prompt is passed in so n8n can customize it."""
    template = prompt_template or DEFAULT_PROMPT
    transcript = _transcript_excerpt(video)
    if not transcript:
        raise MetadataGenerationError(
            "Video chưa có lời thoại — chạy bước tách lời và dịch trước."
        )

    prompt = template.format(title=video.title, transcript=transcript)

    # Reuse translate_service's path: it already handles choosing the provider by the configured API key
    # and falling back when the main provider fails.
    raw = await translate_service.complete_text(db, user_id, prompt)
    return _clean(_extract_json(raw))
