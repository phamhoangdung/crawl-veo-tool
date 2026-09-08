import pytest

from app.models.video import Video
from app.services import metadata_service


class TestExtractJson:
    """Model hay bọc JSON trong markdown hoặc thêm lời dẫn — phải bóc được."""

    def test_plain_json(self) -> None:
        assert metadata_service._extract_json('{"title": "a"}') == {"title": "a"}

    def test_fenced_json(self) -> None:
        raw = '```json\n{"title": "a"}\n```'
        assert metadata_service._extract_json(raw) == {"title": "a"}

    def test_json_with_preamble(self) -> None:
        raw = 'Đây là metadata:\n{"title": "a", "tags": []}'
        assert metadata_service._extract_json(raw)["title"] == "a"

    def test_raises_on_garbage(self) -> None:
        with pytest.raises(metadata_service.MetadataGenerationError):
            metadata_service._extract_json("không phải json")


class TestClean:
    def test_truncates_long_title_and_flags_it(self) -> None:
        """Cắt về giới hạn thay vì từ chối, nhưng phải báo lại để người dùng biết."""
        long_title = "a" * 100
        result = metadata_service._clean({"title": long_title, "description": "", "tags": []})

        assert len(result["title"]) == metadata_service.MAX_TITLE_LENGTH
        assert result["title_truncated"] is True

    def test_keeps_short_title_untouched(self) -> None:
        result = metadata_service._clean({"title": "Ngắn gọn", "description": "", "tags": []})

        assert result["title"] == "Ngắn gọn"
        assert result["title_truncated"] is False

    def test_caps_tag_count(self) -> None:
        result = metadata_service._clean(
            {"title": "t", "description": "d", "tags": [f"tag{i}" for i in range(50)]}
        )
        assert len(result["tags"]) == metadata_service.MAX_TAGS

    def test_drops_blank_tags(self) -> None:
        result = metadata_service._clean(
            {"title": "t", "description": "d", "tags": ["a", "  ", "", "b"]}
        )
        assert result["tags"] == ["a", "b"]


class TestTranscriptExcerpt:
    def test_prefers_translation_over_source(self) -> None:
        video = Video(
            transcript_json=[
                {"text": "有活就干", "translated_text": "Có việc thì làm"},
            ]
        )
        assert "Có việc thì làm" in metadata_service._transcript_excerpt(video)

    def test_falls_back_to_source_when_untranslated(self) -> None:
        video = Video(transcript_json=[{"text": "有活就干", "translated_text": ""}])
        assert "有活就干" in metadata_service._transcript_excerpt(video)

    def test_truncates_long_transcript(self) -> None:
        """Video dài có thể vượt giới hạn token của model."""
        video = Video(transcript_json=[{"text": "x" * 5000, "translated_text": ""}])
        assert len(metadata_service._transcript_excerpt(video, max_chars=100)) == 100

    def test_empty_when_no_transcript(self) -> None:
        assert metadata_service._transcript_excerpt(Video(transcript_json=None)) == ""


class TestGenerateMetadata:
    @pytest.mark.anyio
    async def test_rejects_video_without_transcript(self, dummy_session: object) -> None:
        video = Video(title="t", transcript_json=None)

        with pytest.raises(metadata_service.MetadataGenerationError, match="chưa có lời thoại"):
            await metadata_service.generate_metadata(dummy_session, 1, video)

    @pytest.mark.anyio
    async def test_uses_custom_prompt_template(
        self, dummy_session: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """n8n truyền prompt riêng cho từng loại video."""
        captured: dict[str, str] = {}

        async def fake_complete(db, user_id, prompt: str) -> str:
            captured["prompt"] = prompt
            return '{"title": "x", "description": "y", "tags": []}'

        monkeypatch.setattr(metadata_service.translate_service, "complete_text", fake_complete)

        video = Video(title="Món ngon", transcript_json=[{"text": "a", "translated_text": "b"}])
        await metadata_service.generate_metadata(
            dummy_session, 1, video, prompt_template="Chủ đề ẩm thực: {title} / {transcript}"
        )

        assert captured["prompt"].startswith("Chủ đề ẩm thực: Món ngon")
