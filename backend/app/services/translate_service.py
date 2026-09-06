import logging

import httpx
from sqlalchemy.orm import Session

from app.adapters.translate import google as google_translate
from app.adapters.translate import openai as openai_translate
from app.services import api_key_service

logger = logging.getLogger(__name__)


async def translate_text(db: Session, user_id: int, text: str, source_lang: str, target_lang: str) -> str:
    """Ưu tiên OpenAI nếu đã cấu hình key và gọi được; fallback Google Translate (free) nếu không."""
    api_key = api_key_service.get_decrypted_key(db, user_id, "openai")
    async with httpx.AsyncClient(timeout=30) as client:
        if api_key:
            try:
                return await openai_translate.translate(client, api_key, text, source_lang, target_lang)
            except httpx.HTTPError as exc:
                logger.warning("OpenAI translate failed (%s), falling back to Google Translate", exc)
        return await google_translate.translate(client, text, source_lang, target_lang)
