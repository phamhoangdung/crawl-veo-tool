"""Translate one-off text on demand (tooltip translating Chinese titles).

Unlike the subtitle translation pipeline: this is interactive translation, called on hover, so
it must be cached — without a cache a few passes of the mouse over a 40-row table would exhaust the quota.
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

# Block translating whole articles: the tooltip only needs the title. Longer text is truncated, not rejected.
MAX_TEXT_LENGTH = 500

# Limit per bulk call — one crawl page is 40 videos, leaving a little headroom.
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
    # The key is the original text so the frontend can look it up directly, not by matching order.
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
    """Translate many texts in 1 request — the frontend calls this for the whole page instead of
    40 separate requests. Any text that fails is skipped, without spoiling the whole batch."""
    translations: dict[str, str] = {}

    # Remove duplicates before translating: video lists often have repeated titles.
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
            # Out of quota mid-batch: return what was translated, stop the rest
            # so no more requests are burned for nothing.
            logger.warning("Hết quota giữa lô dịch, trả về %d kết quả", len(translations))
            break
        except Exception:  # noqa: BLE001 — 1 failing text must not spoil the whole batch
            logger.exception("Dịch thất bại cho text: %s", text[:50])

    return BatchTranslateResponse(translations=translations)
