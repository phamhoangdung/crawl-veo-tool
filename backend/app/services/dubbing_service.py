import asyncio
import logging
import re
from pathlib import Path

from pydub import AudioSegment
from sqlalchemy.orm import Session

from app.adapters import diarization_adapter, ffmpeg
from app.adapters.provider_errors import AllProvidersExhaustedError
from app.core import worker_pool
from app.models.video import Video, VideoStatus
from app.services import (
    audio_chunk_service,
    progress_service,
    settings_service,
    transcribe_service,
    translate_service,
    tts_service,
)

logger = logging.getLogger(__name__)

_MIN_STRETCH_FACTOR_DELTA = (
    0.05  # skip time-stretch if off by less than 5%, not worth re-encoding
)

# Number of sentences processed in parallel. Measured on 5 sentences: translation 3.8x faster, TTS 10.2x faster
# than sequential. Capped at 8 so the provider does not block us for rate limiting — higher also
# gains little because the network is the bottleneck.
_MAX_CONCURRENT_SEGMENTS = 8


def _is_speakable(text: str) -> bool:
    """Whether there is any letter or digit to read.

    Edge-TTS reports "No audio was received" when the text is only punctuation — an input error
    rather than a network error, so retrying is useless. Filter beforehand to keep the log clean.
    """
    return bool(re.search(r"[^\W_]", text, flags=re.UNICODE))


def run_transcribe(db: Session, video: Video, source_lang: str = "zh") -> None:
    video.status = VideoStatus.TRANSCRIBING
    db.commit()
    # faster-whisper runs in one go and cannot be split, so only the stage is reported
    # with no percentage.
    progress_service.set_stage(video.id, "transcribing", kind="transcribe")
    try:
        # Dedicated process pool (P2): pure compute, touching no DB/progress_service
        # inside `transcribe_service.transcribe` — safe to separate into another process. This function
        # always already runs in a background thread (not the main event loop), so
        # blocking on `.result()` here does not affect the server.
        future = worker_pool.submit(
            transcribe_service.transcribe, Path(video.local_path), language=source_lang
        )
        video.transcript_json = future.result()
        video.status = VideoStatus.TRANSCRIBED
        db.commit()
    except Exception:
        video.status = VideoStatus.FAILED_TRANSCRIBING
        db.commit()
        raise


def run_diarize(db: Session, video: Video) -> None:
    """Attach speaker labels (SPEAKER_00, SPEAKER_01...) to the existing transcript.

    NOT a mandatory step in the state machine (VideoStatus does not change) — it only
    adds a `speaker` field to each segment so `run_dub_and_mux` can assign a separate
    voice per speaker (Phase 19). Skipping this step still dubs
    normally with 1 shared voice as before.
    """
    segments = video.transcript_json or []
    if not segments:
        raise ValueError("Chưa có lời thoại để phân vai người nói.")

    video_dir = Path(video.local_path).parent
    audio_path = video_dir / "original_audio.wav"
    if not audio_path.exists():
        ffmpeg.extract_audio(Path(video.local_path), audio_path)

    # Dedicated process pool (P2) — same reason as `run_transcribe`.
    future = worker_pool.submit(
        diarization_adapter.assign_speakers, audio_path, segments
    )
    video.transcript_json = future.result()
    db.commit()


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
        # Translate in parallel with a limit — sequentially 32 sentences take ~8s, in parallel ~2s.
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SEGMENTS)

        async def translate_one(segment: dict) -> dict:
            async with semaphore:
                text = await translate_service.translate_text(
                    db, user_id, segment["text"], source_lang, target_lang
                )
            progress_service.advance(video.id, 1, kind="translate")
            return {**segment, "translated_text": text}

        # Build a NEW list instead of editing in place: SQLAlchemy JSON columns do not track
        # changes inside, reassigning the same old object makes commit write nothing.
        # gather preserves input order so the timeline is not shuffled.
        translated = list(
            await asyncio.gather(*(translate_one(seg) for seg in segments))
        )

        video.transcript_json = translated
        video.status = VideoStatus.TRANSLATED
        db.commit()
    except AllProvidersExhaustedError:
        # Every key in the pool + the free provider is out of quota — pause to retry
        # later, NOT an error needing a fix (unlike FAILED_TRANSLATING).
        video.status = VideoStatus.PAUSED_QUOTA
        db.commit()
        raise
    except Exception:
        video.status = VideoStatus.FAILED_TRANSLATING
        db.commit()
        raise


async def _synthesize_segment_matched_duration(
    db: Session,
    user_id: int,
    text: str,
    target_duration_s: float,
    tmp_dir: Path,
    index: int,
    voice: dict[str, str] | None = None,
) -> AudioSegment | None:
    """Generate speech then stretch (time-stretch, keeping pitch) to match the original segment duration."""
    raw_path = tmp_dir / f"segment_{index}_raw.mp3"
    try:
        await tts_service.synthesize_speech(db, user_id, text, raw_path, voice=voice)
    except tts_service.TtsFailedError as exc:
        logger.warning("Skipping segment %d (TTS failed): %s", index, exc)
        return None

    raw_clip = AudioSegment.from_file(raw_path)
    raw_duration_s = len(raw_clip) / 1000
    if raw_duration_s <= 0 or target_duration_s <= 0:
        raw_path.unlink(missing_ok=True)
        return raw_clip

    factor = raw_duration_s / target_duration_s
    if abs(factor - 1.0) < _MIN_STRETCH_FACTOR_DELTA:
        raw_path.unlink(missing_ok=True)
        return raw_clip

    stretched_path = tmp_dir / f"segment_{index}_stretched.mp3"
    ffmpeg.time_stretch(raw_path, stretched_path, factor)
    stretched_clip = AudioSegment.from_file(stretched_path)
    # Both files are loaded into memory (the real audio is in `stretched_clip`) — clean up
    # right away instead of leaving them until the 30-day cleanup (storage_cleanup_service).
    raw_path.unlink(missing_ok=True)
    stretched_path.unlink(missing_ok=True)
    return stretched_clip


async def run_dub_and_mux(
    db: Session, user_id: int, video: Video, keep_background: bool = True
) -> Path:
    """Generate speech for each segment (time-stretch to match the original sentence duration), optionally separating
    and keeping the background music (Demucs) before replacing the audio track, instead of wiping the original audio."""
    video.status = VideoStatus.DUBBING
    db.commit()
    try:
        segments = video.transcript_json or []
        # If speaker separation is turned off in Settings, ignore speaker labels that already exist (from when
        # it was on) — dub with 1 shared voice as if speakers were never separated.
        speaker_voices = (
            video.speaker_voices_json or {}
            if settings_service.get_speaker_diarization_enabled(db, user_id)
            else {}
        )
        video_dir = Path(video.local_path).parent
        segments_dir = video_dir / "tts_segments"
        segments_dir.mkdir(exist_ok=True)

        total_ms = int((video.duration_seconds or 60) * 1000)
        voice_timeline = AudioSegment.silent(duration=total_ms)
        progress_service.set_stage(
            video.id, "synthesizing", total=len(segments), kind="dub"
        )
        # Generate speech in parallel (mostly network calls, waiting on I/O) and only then join sequentially
        # — joining is CPU audio processing, parallel is no faster.
        # Measured: 32 sentences sequential ~54s, parallel ~5s.
        tts_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SEGMENTS)

        async def synthesize_one(
            index: int, segment: dict
        ) -> tuple[int, AudioSegment | None]:
            # ONLY use the translation: a Vietnamese voice cannot read the original Chinese,
            # Edge-TTS would report "No audio was received".
            text = (segment.get("translated_text") or "").strip()
            if not _is_speakable(text):
                logger.debug(
                    "Bỏ qua đoạn %d: không có nội dung đọc được (%r)", index, text
                )
                progress_service.advance(video.id, 1, kind="dub")
                return index, None

            target_duration = max(segment["end"] - segment["start"], 0.3)
            speaker = segment.get("speaker")
            voice = speaker_voices.get(speaker) if speaker else None
            async with tts_semaphore:
                clip = await _synthesize_segment_matched_duration(
                    db, user_id, text, target_duration, segments_dir, index, voice=voice
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
            # Demucs runs the PyTorch model in one go — only the stage is reported, no %.
            progress_service.set_stage(video.id, "separating", kind="dub")
            original_audio_path = video_dir / "original_audio.wav"
            if not original_audio_path.exists():
                # If the "Speaker separation" step (Phase 19) ran earlier, this file
                # already exists — extracting it again is wasteful (heavy I/O for long videos).
                await asyncio.to_thread(
                    ffmpeg.extract_audio, Path(video.local_path), original_audio_path
                )

            def report_chunk(done: int, total: int) -> None:
                """A long video is cut into several chunks — report progress per chunk, otherwise
                the progress bar would sit still for tens of minutes and look hung.

                Only set `total` at the first chunk: `set_stage` resets `current` to 0 on every
                call, calling it again per chunk would leave the progress bar forever at 1/total.
                """
                if done == 1:
                    progress_service.set_stage(
                        video.id, "separating", total=total, kind="dub"
                    )
                progress_service.advance(video.id, 1, "dub")

            # to_thread for the whole block below: Demucs + ffmpeg are both blocking,
            # calling directly in this coroutine (which runs straight on the main event loop
            # when queued as a background task) would freeze the whole server until
            # done — see docs/performance-optimization/plan.md, section P0.
            _vocals_path, background_path = await asyncio.to_thread(
                audio_chunk_service.separate_vocals,
                original_audio_path,
                video_dir / "demucs_out",
                duration=video.duration_seconds,
                on_chunk_done=report_chunk,
            )

            voice_path = video_dir / "voice_timeline.mp3"
            await asyncio.to_thread(voice_timeline.export, voice_path, format="mp3")
            final_audio_path = video_dir / "dubbed_audio.mp3"
            await asyncio.to_thread(
                ffmpeg.mix_audio_tracks, voice_path, background_path, final_audio_path
            )
        else:
            final_audio_path = video_dir / "dubbed_audio.mp3"
            await asyncio.to_thread(
                voice_timeline.export, final_audio_path, format="mp3"
            )

        video.status = VideoStatus.MUXING
        db.commit()
        progress_service.set_stage(video.id, "muxing", kind="dub")

        output_path = video_dir / "dubbed.mp4"
        await asyncio.to_thread(
            ffmpeg.replace_audio_track,
            Path(video.local_path),
            final_audio_path,
            output_path,
        )

        video.dubbed_path = str(output_path)
        video.status = VideoStatus.DONE
        db.commit()
        return output_path
    except Exception:
        video.status = VideoStatus.FAILED_DUBBING
        db.commit()
        raise
