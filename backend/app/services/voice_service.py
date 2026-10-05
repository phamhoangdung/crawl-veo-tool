import logging

import httpx
from sqlalchemy.orm import Session

from app.services import api_key_service

logger = logging.getLogger(__name__)

# The 2 standard Vietnamese Edge-TTS voices (free, always available with no configuration
# needed) — one male and one female are enough for the MVP of speaker separation (Phase 19).
_EDGE_VOICES: list[dict[str, str]] = [
    {
        "provider": "edge",
        "voice_id": "vi-VN-HoaiMyNeural",
        "name": "Hoài My (Edge-TTS, miễn phí)",
        "gender": "female",
    },
    {
        "provider": "edge",
        "voice_id": "vi-VN-NamMinhNeural",
        "name": "Nam Minh (Edge-TTS, miễn phí)",
        "gender": "male",
    },
]

_ELEVENLABS_VOICES_ENDPOINT = "https://api.elevenlabs.io/v1/voices"


async def list_available_voices(db: Session, user_id: int) -> list[dict[str, str]]:
    """Combine the Edge-TTS voices (always present) with the user's real ElevenLabs voices if a
    key is configured — only "peek" at the key (not counted in the Phase 8 usage pool, see
    `api_key_service.get_decrypted_key`)."""
    voices = list(_EDGE_VOICES)

    api_key = api_key_service.get_decrypted_key(db, user_id, "elevenlabs")
    if not api_key:
        return voices

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                _ELEVENLABS_VOICES_ENDPOINT, headers={"xi-api-key": api_key}
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logger.warning("Không lấy được danh sách giọng ElevenLabs: %s", exc)
        return voices

    for item in data.get("voices", []):
        voices.append(
            {
                "provider": "elevenlabs",
                "voice_id": item["voice_id"],
                "name": item.get("name") or item["voice_id"],
                "gender": (item.get("labels") or {}).get("gender", "unknown"),
            }
        )
    return voices
