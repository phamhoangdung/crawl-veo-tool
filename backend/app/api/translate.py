"""Dịch text lẻ theo yêu cầu (tooltip dịch tiêu đề tiếng Trung).

Khác pipeline dịch phụ đề: đây là dịch tương tác, gọi khi người dùng hover nên
phải có cache — không cache thì rê chuột qua bảng 40 dòng vài lượt là hết quota.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services import translate_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/translate", tags=["translate"])

_DEFAULT_USER_ID = 1

# Chặn dịch cả bài: tooltip chỉ cần tiêu đề. Text dài hơn thì cắt, không từ chối.
MAX_TEXT_LENGTH = 500

# Giới hạn mỗi lần gọi hàng loạt — một trang crawl là 40 video, để dư một chút.
MAX_BATCH_SIZE = 60


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1)
    source_lang: str = "zh"
    target_lang: str = "vi"


class TranslateResponse(BaseModel):
    translated_text: str
    cached: bool


class BatchTranslateRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=MAX_BATCH_SIZE)
    source_lang: str = "zh"
    target_lang: str = "vi"


class BatchTranslateResponse(BaseModel):
    # Khoá là text gốc để frontend tra cứu trực tiếp, không phải khớp theo thứ tự.
    translations: dict[str, str]


@router.post("", response_model=TranslateResponse)
async def translate_one(
    payload: TranslateRequest, db: Session = Depends(get_db)
) -> TranslateResponse:
    try:
        translated, cached = await translate_service.translate_cached(
            db,
            _DEFAULT_USER_ID,
            payload.text[:MAX_TEXT_LENGTH],
            payload.source_lang,
            payload.target_lang,
        )
    except translate_service.AllProvidersExhaustedError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    return TranslateResponse(translated_text=translated, cached=cached)


@router.post("/batch", response_model=BatchTranslateResponse)
async def translate_batch(
    payload: BatchTranslateRequest, db: Session = Depends(get_db)
) -> BatchTranslateResponse:
    """Dịch nhiều text trong 1 request — frontend gọi cái này cho cả trang thay vì
    40 request rời rạc. Text nào lỗi thì bỏ qua, không làm hỏng cả lô."""
    translations: dict[str, str] = {}

    # Bỏ trùng trước khi dịch: danh sách video hay có tiêu đề lặp lại.
    for text in dict.fromkeys(t for t in payload.texts if t.strip()):
        try:
            translated, _ = await translate_service.translate_cached(
                db,
                _DEFAULT_USER_ID,
                text[:MAX_TEXT_LENGTH],
                payload.source_lang,
                payload.target_lang,
            )
            translations[text] = translated
        except translate_service.AllProvidersExhaustedError:
            # Hết quota giữa lô: trả về những gì đã dịch được, dừng phần còn lại
            # để không đốt thêm request vô ích.
            logger.warning("Hết quota giữa lô dịch, trả về %d kết quả", len(translations))
            break
        except Exception:  # noqa: BLE001 — 1 text lỗi không được làm hỏng cả lô
            logger.exception("Dịch thất bại cho text: %s", text[:50])

    return BatchTranslateResponse(translations=translations)
