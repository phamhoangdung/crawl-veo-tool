from pathlib import Path
from unittest.mock import patch

from app.services import audio_chunk_service


class TestPlanChunks:
    def test_short_audio_is_one_chunk(self) -> None:
        assert audio_chunk_service.plan_chunks(120.0, []) == [(0.0, 120.0)]

    def test_zero_duration_gives_nothing(self) -> None:
        assert audio_chunk_service.plan_chunks(0.0, []) == []

    def test_cuts_at_silence_nearest_the_target(self) -> None:
        """Có nhiều khoảng lặng hợp lệ thì chọn cái gần `target` nhất, không phải
        cái đầu tiên gặp — cắt quá sớm sẽ tạo ra nhiều khúc hơn mức cần."""
        silences = [(160.0, 162.0), (298.0, 302.0), (400.0, 402.0)]
        chunks = audio_chunk_service.plan_chunks(900.0, silences)
        assert chunks[0] == (0.0, 300.0), "khoảng lặng ở 300s gần target 300s nhất"

    def test_falls_back_to_hard_cut_when_no_silence_in_range(self) -> None:
        """Nhạc nền liên tục không có chỗ lặng nào — thà cắt cứng ở `max` còn hơn
        để một khúc dài vô hạn làm tràn RAM."""
        chunks = audio_chunk_service.plan_chunks(
            1000.0, [], target_seconds=300.0, max_seconds=420.0
        )
        assert chunks[0] == (0.0, 420.0)

    def test_ignores_silence_too_early_to_be_useful(self) -> None:
        """Khoảng lặng ở giây thứ 5 mà cắt luôn thì sinh ra hàng trăm khúc tí hon."""
        chunks = audio_chunk_service.plan_chunks(1000.0, [(5.0, 7.0)])
        assert chunks[0][1] > 100.0

    def test_chunks_are_contiguous_and_cover_whole_duration(self) -> None:
        chunks = audio_chunk_service.plan_chunks(
            3600.0, [(t, t + 2) for t in range(250, 3600, 250)]
        )
        assert chunks[0][0] == 0.0
        assert chunks[-1][1] == 3600.0
        for earlier, later in zip(chunks, chunks[1:]):
            assert earlier[1] == later[0], "không được hở hay chồng lấn giữa 2 khúc"

    def test_no_chunk_exceeds_max(self) -> None:
        chunks = audio_chunk_service.plan_chunks(5000.0, [], max_seconds=420.0)
        assert all(end - start <= 420.0 + 1e-6 for start, end in chunks)


class TestSeparateVocalsDispatch:
    def test_short_audio_goes_straight_to_demucs(self, tmp_path: Path) -> None:
        """Dưới ngưỡng thì KHÔNG được cắt: thêm bước cắt/ghép chỉ tổ chậm."""
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"x")
        with (
            patch.object(audio_chunk_service.demucs, "separate_vocals") as separate,
            patch.object(audio_chunk_service.ffmpeg, "detect_silences") as detect,
        ):
            separate.return_value = (tmp_path / "v.wav", tmp_path / "n.wav")
            audio_chunk_service.separate_vocals(audio, tmp_path / "out", duration=300.0)

        separate.assert_called_once()
        detect.assert_not_called()

    def test_long_audio_is_chunked_and_reported(self, tmp_path: Path) -> None:
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"x")
        reported: list[tuple[int, int]] = []

        with (
            patch.object(audio_chunk_service.demucs, "separate_vocals") as separate,
            patch.object(audio_chunk_service.ffmpeg, "detect_silences", return_value=[]),
            patch.object(audio_chunk_service.ffmpeg, "slice_audio"),
            patch.object(audio_chunk_service.ffmpeg, "concat_audio") as concat,
        ):
            separate.side_effect = lambda part, out: (out / "vocals.wav", out / "no_vocals.wav")
            vocals, background = audio_chunk_service.separate_vocals(
                audio,
                tmp_path / "out",
                duration=1500.0,
                on_chunk_done=lambda done, total: reported.append((done, total)),
            )

        assert separate.call_count == len(reported) > 1
        assert reported[-1][0] == reported[-1][1], "khúc cuối phải báo done == total"
        assert concat.call_count == 2, "ghép lại cả vocals lẫn nhạc nền"
        # Đường dẫn quy ước mà timeline_service.get_audio_stems đọc — đổi là mất
        # track nhạc nền trong editor mà không báo lỗi gì.
        assert background == tmp_path / "out" / "htdemucs" / "a" / "no_vocals.wav"
        assert vocals == tmp_path / "out" / "htdemucs" / "a" / "vocals.wav"
