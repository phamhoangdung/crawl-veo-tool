"""Uses the unofficial translate.googleapis.com endpoint — free, no API key needed.

Not the official Google Cloud Translation API, only suitable for an MVP/personal
use; for heavy/real production use, switch fully to OpenAI or the official
Google Cloud Translation (see docs/overview/plan.md, legal section).
"""

import httpx

_ENDPOINT = "https://translate.googleapis.com/translate_a/single"


async def translate(client: httpx.AsyncClient, text: str, source_lang: str, target_lang: str) -> str:
    response = await client.get(
        _ENDPOINT,
        params={"client": "gtx", "sl": source_lang, "tl": target_lang, "dt": "t", "q": text},
    )
    response.raise_for_status()
    segments = response.json()[0]
    return "".join(segment[0] for segment in segments)
