import logging
from pathlib import Path

from pydub import AudioSegment
from sqlalchemy.orm import Session

from app.adapters import ffmpeg
from app.models.video import Video, VideoStatus
from app.services import transcribe_service, translate_service, tts_service

logger = logging.getLogger(__name__)


def run_transcribe(db: Session, video: Video, source_lang: str = "zh") -> None:
    video.status = VideoStatus.TRANSCRIBING
    db.commit()
    try:
        video.transcript_json = transcribe_service.transcribe(Path(video.local_path), language=source_lang)
        db.commit()
    except Exception:
        video.status = VideoStatus.FAILED_TRANSCRIBING
        db.commit()
        raise


async def run_translate(
    db: Session, user_id: int, video: Video, source_lang: str, target_lang: str
) -> None:
    video.status = VideoStatus.TRANSLATING
    db.commit()
    try:
        segments = video.transcript_json or []
        for segment in segments:
            segment["translated_text"] = await translate_service.translate_text(
                db, user_id, segment["text"], source_lang, target_lang
            )
        video.transcript_json = segments
        db.commit()
    except Exception:
        video.status = VideoStatus.FAILED_TRANSLATING
        db.commit()
        raise


async def run_dub_and_mux(db: Session, user_id: int, video: Video) -> Path:
    """Sinh giọng đọc cho từng đoạn, đặt đúng mốc thời gian gốc, rồi thay hẳn audio track.

    Chưa time-stretch để khớp chính xác thời lượng câu (việc của Phase 4) — đoạn TTS
    dài hơn bản gốc sẽ tràn nhẹ sang khoảng lặng của đoạn sau, chấp nhận được ở MVP.
    """
    video.status = VideoStatus.DUBBING
    db.commit()
    try:
        segments = video.transcript_json or []
        video_dir = Path(video.local_path).parent
        segments_dir = video_dir / "tts_segments"
        segments_dir.mkdir(exist_ok=True)

        total_ms = int((video.duration_seconds or 60) * 1000)
        timeline = AudioSegment.silent(duration=total_ms)
        for i, segment in enumerate(segments):
            text = (segment.get("translated_text") or segment.get("text") or "").strip()
            if not text:
                continue
            segment_path = segments_dir / f"segment_{i}.mp3"
            try:
                await tts_service.synthesize_speech(db, user_id, text, segment_path)
            except tts_service.TtsFailedError as exc:
                logger.warning("Skipping segment %d (TTS failed): %s", i, exc)
                continue
            clip = AudioSegment.from_file(segment_path)
            timeline = timeline.overlay(clip, position=int(segment["start"] * 1000))

        video.status = VideoStatus.MUXING
        db.commit()

        dubbed_audio_path = video_dir / "dubbed_audio.mp3"
        timeline.export(dubbed_audio_path, format="mp3")

        output_path = video_dir / "dubbed.mp4"
        ffmpeg.replace_audio_track(Path(video.local_path), dubbed_audio_path, output_path)

        video.dubbed_path = str(output_path)
        video.status = VideoStatus.DONE
        db.commit()
        return output_path
    except Exception:
        video.status = VideoStatus.FAILED_DUBBING
        db.commit()
        raise
