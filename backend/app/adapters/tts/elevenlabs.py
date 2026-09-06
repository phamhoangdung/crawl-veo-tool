from pathlib import Path

import httpx

_ENDPOINT = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

# Giọng multilingual mặc định có sẵn trên mọi tài khoản ElevenLabs.
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"


async def synthesize(
    client: httpx.AsyncClient,
    api_key: str,
    text: str,
    output_path: Path,
    voice_id: str = DEFAULT_VOICE_ID,
) -> None:
    response = await client.post(
        _ENDPOINT.format(voice_id=voice_id),
        headers={"xi-api-key": api_key},
        json={"text": text, "model_id": "eleven_multilingual_v2"},
    )
    response.raise_for_status()
    output_path.write_bytes(response.content)
