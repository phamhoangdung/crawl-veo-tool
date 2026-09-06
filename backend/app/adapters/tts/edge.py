from pathlib import Path

import edge_tts

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"


async def synthesize(text: str, output_path: Path, voice: str = DEFAULT_VOICE) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))
