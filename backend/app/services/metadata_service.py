"""Sinh tiêu đề / mô tả / tag cho video trước khi đăng.

Quy tắc SEO lấy từ skill `youtube-seo` (.claude/skills/youtube-seo): tiêu đề dưới
60 ký tự với từ khoá chính ở 5–55 ký tự đầu, 2–3 câu mở mô tả chứa từ khoá tự
nhiên, tag chỉ là phụ trợ (tiêu đề + mô tả quan trọng hơn).

Prompt truyền được từ ngoài để n8n dùng kịch bản riêng cho từng loại video —
mỗi chủ đề (ẩm thực, vlog, tin tức) cần văn phong khác nhau.
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

# Nhắc mô hình bám quy tắc SEO thật thay vì viết tuỳ hứng. `{transcript}` và
# `{title}` được thay bằng nội dung video.
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
    """Lấy phần lời thoại đã dịch làm ngữ cảnh. Cắt bớt vì video dài có thể vượt
    giới hạn token của model."""
    segments = video.transcript_json or []
    lines = [
        (s.get("translated_text") or s.get("text") or "").strip()
        for s in segments
        if (s.get("translated_text") or s.get("text") or "").strip()
    ]
    text = " ".join(lines)
    return text[:max_chars] if len(text) > max_chars else text


def _extract_json(raw: str) -> dict:
    """Model hay bọc JSON trong ```json ... ``` hoặc thêm lời dẫn — bóc ra."""
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
    """Cắt về đúng giới hạn thay vì từ chối — metadata hơi dài vẫn dùng được."""
    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    raw_tags = data.get("tags") or []

    tags = [str(t).strip() for t in raw_tags if str(t).strip()][:MAX_TAGS]

    return {
        "title": title[:MAX_TITLE_LENGTH],
        "description": description[:MAX_DESCRIPTION_LENGTH],
        "tags": tags,
        # Báo lại để người dùng biết đã bị cắt, không âm thầm mất chữ.
        "title_truncated": len(title) > MAX_TITLE_LENGTH,
    }


async def generate_metadata(
    db: Session,
    user_id: int,
    video: Video,
    prompt_template: str | None = None,
) -> dict:
    """Sinh metadata bằng LLM đã cấu hình. Prompt truyền ngoài để n8n tuỳ biến."""
    template = prompt_template or DEFAULT_PROMPT
    transcript = _transcript_excerpt(video)
    if not transcript:
        raise MetadataGenerationError(
            "Video chưa có lời thoại — chạy bước tách lời và dịch trước."
        )

    prompt = template.format(title=video.title, transcript=transcript)

    # Dùng lại đường đi của translate_service: nó đã lo chọn provider theo API key
    # đã cấu hình và fallback khi provider chính lỗi.
    raw = await translate_service.complete_text(db, user_id, prompt)
    return _clean(_extract_json(raw))
