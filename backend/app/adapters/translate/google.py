"""Dùng endpoint không chính thức translate.googleapis.com — miễn phí, không cần API key.

Không phải API chính thức của Google Cloud Translation, chỉ phù hợp cho MVP/cá
nhân; dùng khối lượng lớn/production thật nên chuyển hẳn sang OpenAI hoặc
Google Cloud Translation chính thức (xem docs/overview/plan.md phần pháp lý).
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
