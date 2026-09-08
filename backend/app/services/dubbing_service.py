import asyncio
import logging
import re
from pathlib import Path

from pydub import AudioSegment
from sqlalchemy.orm import Session

from app.adapters import demucs, ffmpeg
from app.adapters.provider_errors import AllProvidersExhaustedError
from app.models.video import Video, VideoStatus
from app.services import (
    progress_service,
    transcribe_service,
    translate_service,
    tts_service,
)

logger = logging.getLogger(__name__)

_MIN_STRETCH_FACTOR_DELTA = 0.05  # bỏ qua time-stretch nếu lệch dưới 5%, không đáng để re-encode

# Số câu xử lý song song. Đo thật trên 5 câu: dịch nhanh 3.8x, TTS nhanh 10.2x so
# với tuần tự. Giới hạn 8 để không bị provider chặn vì rate limit — cao hơn cũng
# không nhanh thêm bao nhiêu vì nghẽn ở mạng.
_MAX_CONCURRENT_SEGMENTS = 8


def _is_speakable(text: str) -> bool:
    """Có chữ hoặc số để đọc không.

    Edge-TTS báo "No audio was received" khi văn bản chỉ có dấu câu — lỗi input
    chứ không phải lỗi mạng, nên retry cũng vô ích. Lọc trước cho sạch log.
    """
    return bool(re.search(r"[^\W_]", text, flags=re.UNICODE))


def run_transcribe(db: Session, video: Video, source_lang: str = "zh") -> None:
    video.status = VideoStatus.TRANSCRIBING
    db.commit()
    # faster-whisper chạy liền một mạch, không chia nhỏ được nên chỉ báo chặng
    # chứ không có phần trăm.
    progress_service.set_stage(video.id, "transcribing", kind="transcribe")
    try:
        video.transcript_json = transcribe_service.transcribe(Path(video.local_path), language=source_lang)
        video.status = VideoStatus.TRANSCRIBED
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
        progress_service.set_stage(
            video.id, "translating", total=len(segments), kind="translate"
        )
        # Dịch song song có giới hạn — tuần tự thì 32 câu mất ~8s, song song ~2s.
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SEGMENTS)

        async def translate_one(segment: dict) -> dict:
            async with semaphore:
                text = await translate_service.translate_text(
                    db, user_id, segment["text"], source_lang, target_lang
                )
            progress_service.advance(video.id, 1, kind="translate")
            return {**segment, "translated_text": text}

        # Dựng list MỚI thay vì sửa tại chỗ: cột JSON của SQLAlchemy không theo
        # dõi thay đổi bên trong, gán lại chính object cũ thì commit không ghi gì.
        # gather giữ nguyên thứ tự đầu vào nên timeline không bị xáo.
        translated = list(await asyncio.gather(*(translate_one(seg) for seg in segments)))

        video.transcript_json = translated
        video.status = VideoStatus.TRANSLATED
        db.commit()
    except AllProvidersExhaustedError:
        # Hết quota toàn bộ key trong pool + provider free — tạm dừng để thử lại
        # sau, KHÔNG phải lỗi cần sửa (khác FAILED_TRANSLATING).
        video.status = VideoStatus.PAUSED_QUOTA
        db.commit()
        raise
    except Exception:
        video.status = VideoStatus.FAILED_TRANSLATING
        db.commit()
        raise


async def _synthesize_segment_matched_duration(
    db: Session, user_id: int, text: str, target_duration_s: float, tmp_dir: Path, index: int
) -> AudioSegment | None:
    """Sinh giọng rồi co giãn (time-stretch, giữ cao độ) cho khớp thời lượng đoạn gốc."""
    raw_path = tmp_dir / f"segment_{index}_raw.mp3"
    try:
        await tts_service.synthesize_speech(db, user_id, text, raw_path)
    except tts_service.TtsFailedError as exc:
        logger.warning("Skipping segment %d (TTS failed): %s", index, exc)
        return None

    raw_clip = AudioSegment.from_file(raw_path)
    raw_duration_s = len(raw_clip) / 1000
    if raw_duration_s <= 0 or target_duration_s <= 0:
        return raw_clip

    factor = raw_duration_s / target_duration_s
    if abs(factor - 1.0) < _MIN_STRETCH_FACTOR_DELTA:
        return raw_clip

    stretched_path = tmp_dir / f"segment_{index}_stretched.mp3"
    ffmpeg.time_stretch(raw_path, stretched_path, factor)
    return AudioSegment.from_file(stretched_path)


async def run_dub_and_mux(db: Session, user_id: int, video: Video, keep_background: bool = True) -> Path:
    """Sinh giọng đọc cho từng đoạn (time-stretch khớp thời lượng câu gốc), tuỳ chọn tách
    và giữ lại nhạc nền (Demucs) trước khi thay audio track, thay vì xoá sạch âm thanh gốc."""
    video.status = VideoStatus.DUBBING
    db.commit()
    try:
        segments = video.transcript_json or []
        video_dir = Path(video.local_path).parent
        segments_dir = video_dir / "tts_segments"
        segments_dir.mkdir(exist_ok=True)

        total_ms = int((video.duration_seconds or 60) * 1000)
        voice_timeline = AudioSegment.silent(duration=total_ms)
        progress_service.set_stage(
            video.id, "synthesizing", total=len(segments), kind="dub"
        )
        # Sinh giọng song song (gọi mạng, chờ I/O là chính) rồi mới ghép tuần tự
        # — ghép là xử lý audio trên CPU, chạy song song không nhanh hơn.
        # Đo thật: 32 câu tuần tự ~54s, song song ~5s.
        tts_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SEGMENTS)

        async def synthesize_one(index: int, segment: dict) -> tuple[int, AudioSegment | None]:
            # CHỈ dùng bản dịch: giọng tiếng Việt không đọc được lời gốc tiếng
            # Trung, Edge-TTS sẽ báo "No audio was received".
            text = (segment.get("translated_text") or "").strip()
            if not _is_speakable(text):
                logger.debug("Bỏ qua đoạn %d: không có nội dung đọc được (%r)", index, text)
                progress_service.advance(video.id, 1, kind="dub")
                return index, None

            target_duration = max(segment["end"] - segment["start"], 0.3)
            async with tts_semaphore:
                clip = await _synthesize_segment_matched_duration(
                    db, user_id, text, target_duration, segments_dir, index
                )
            progress_service.advance(video.id, 1, kind="dub")
            return index, clip

        results = await asyncio.gather(
            *(synthesize_one(i, seg) for i, seg in enumerate(segments))
        )

        for index, clip in results:
            if clip is None:
                continue
            voice_timeline = voice_timeline.overlay(
                clip, position=int(segments[index]["start"] * 1000)
            )

        if keep_background:
            video.status = VideoStatus.SEPARATING_AUDIO
            db.commit()
            # Demucs chạy model PyTorch liền mạch — chỉ báo chặng, không có %.
            progress_service.set_stage(video.id, "separating", kind="dub")
            original_audio_path = video_dir / "original_audio.wav"
            ffmpeg.extract_audio(Path(video.local_path), original_audio_path)
            _vocals_path, background_path = demucs.separate_vocals(
                original_audio_path, video_dir / "demucs_out"
            )

            voice_path = video_dir / "voice_timeline.mp3"
            voice_timeline.export(voice_path, format="mp3")
            final_audio_path = video_dir / "dubbed_audio.mp3"
            ffmpeg.mix_audio_tracks(voice_path, background_path, final_audio_path)
        else:
            final_audio_path = video_dir / "dubbed_audio.mp3"
            voice_timeline.export(final_audio_path, format="mp3")

        video.status = VideoStatus.MUXING
        db.commit()
        progress_service.set_stage(video.id, "muxing", kind="dub")

        output_path = video_dir / "dubbed.mp4"
        ffmpeg.replace_audio_track(Path(video.local_path), final_audio_path, output_path)

        video.dubbed_path = str(output_path)
        video.status = VideoStatus.DONE
        db.commit()
        return output_path
    except Exception:
        video.status = VideoStatus.FAILED_DUBBING
        db.commit()
        raise
