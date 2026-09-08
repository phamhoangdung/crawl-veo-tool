import httpx

_ENDPOINT = "https://api.openai.com/v1/chat/completions"


async def translate(
    client: httpx.AsyncClient, api_key: str, text: str, source_lang: str, target_lang: str
) -> str:
    response = await client.post(
        _ENDPOINT,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"Dịch văn bản sau từ {source_lang} sang {target_lang}. "
                        "Chỉ trả về bản dịch, không thêm giải thích hay chú thích."
                    ),
                },
                {"role": "user", "content": text},
            ],
            "temperature": 0.3,
        },
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


async def complete(
    client: httpx.AsyncClient, api_key: str, prompt: str, *, temperature: float = 0.7
) -> str:
    """Gọi model với prompt tự do — dùng cho sinh metadata, không phải dịch.

    Temperature cao hơn `translate` vì viết tiêu đề/mô tả cần đa dạng, tránh mọi
    video ra cùng một khuôn (đúng thứ chính sách inauthentic content nhắm tới).
    """
    response = await client.post(
        _ENDPOINT,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        },
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()
