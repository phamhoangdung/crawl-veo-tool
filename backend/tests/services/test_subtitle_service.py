from app.services.subtitle_service import build_bilingual_srt, pick_font_size_for


def test_build_bilingual_srt_formats_timestamps_and_both_languages():
    segments = [
        {"start": 0.0, "end": 1.5, "text": "hello", "translated_text": "xin chao"},
        {"start": 61.25, "end": 63.0, "text": "bye", "translated_text": "tam biet"},
    ]

    srt = build_bilingual_srt(segments)

    assert "00:00:00,000 --> 00:00:01,500" in srt
    assert "00:01:01,250 --> 00:01:03,000" in srt
    assert "hello" in srt and "xin chao" in srt
    assert "bye" in srt and "tam biet" in srt


def test_build_bilingual_srt_skips_empty_segments():
    segments = [{"start": 0.0, "end": 1.0, "text": "", "translated_text": ""}]

    srt = build_bilingual_srt(segments)

    assert srt == ""


def test_pick_font_size_larger_relative_for_portrait_video():
    landscape_size = pick_font_size_for(1920, 1080)
    portrait_size = pick_font_size_for(1080, 1920)

    assert portrait_size > landscape_size
    assert landscape_size > 0
