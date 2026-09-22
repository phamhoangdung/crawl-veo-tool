from pathlib import Path

import pytest

from app.services import font_service


class TestListFonts:
    def test_returns_non_empty_catalog(self) -> None:
        fonts = font_service.list_fonts()
        assert len(fonts) > 0
        assert all(f.id and f.label and f.family_name and f.regular_file for f in fonts)

    def test_every_registered_file_exists_on_disk(self) -> None:
        """Bắt lỗi gõ nhầm tên file — nếu sai, `resolve_fontfile` sẽ trả về
        đường dẫn không tồn tại và ffmpeg chỉ báo lỗi khi render, khó truy ra
        nguyên nhân."""
        for font in font_service.list_fonts():
            assert (font_service.fonts_dir() / font.regular_file).exists(), font.regular_file
            if font.bold_file:
                assert (font_service.fonts_dir() / font.bold_file).exists(), font.bold_file


class TestGetFont:
    def test_known_id(self) -> None:
        font = font_service.get_font(font_service.DEFAULT_FONT_ID)
        assert font.id == font_service.DEFAULT_FONT_ID

    def test_unknown_id_raises(self) -> None:
        with pytest.raises(font_service.FontNotFoundError):
            font_service.get_font("khong-ton-tai")


class TestGetFontOrDefault:
    def test_unknown_id_falls_back(self) -> None:
        font = font_service.get_font_or_default("khong-ton-tai")
        assert font.id == font_service.DEFAULT_FONT_ID

    def test_none_falls_back(self) -> None:
        font = font_service.get_font_or_default(None)
        assert font.id == font_service.DEFAULT_FONT_ID

    def test_known_id_passthrough(self) -> None:
        font = font_service.get_font_or_default("barlow")
        assert font.id == "barlow"


class TestResolveFontfile:
    def test_known_font_regular(self) -> None:
        path = font_service.resolve_fontfile("barlow", bold=False)
        assert path.name == "Barlow-Regular.ttf"
        assert path.exists()

    def test_known_font_bold(self) -> None:
        path = font_service.resolve_fontfile("barlow", bold=True)
        assert path.name == "Barlow-Bold.ttf"

    def test_font_without_bold_file_falls_back_to_regular(self) -> None:
        path = font_service.resolve_fontfile("anton", bold=True)
        assert path.name == "Anton-Regular.ttf"

    def test_unknown_or_missing_id_falls_back_to_default(self) -> None:
        path = font_service.resolve_fontfile("khong-ton-tai", bold=False)
        default = font_service.get_font(font_service.DEFAULT_FONT_ID)
        assert path.name == default.regular_file

    def test_none_id_falls_back_to_default(self) -> None:
        path = font_service.resolve_fontfile(None, bold=False)
        default = font_service.get_font(font_service.DEFAULT_FONT_ID)
        assert path.name == default.regular_file


class TestFontsDir:
    def test_matches_resolved_file_parent(self) -> None:
        resolved = font_service.resolve_fontfile("barlow")
        assert font_service.fonts_dir() == resolved.parent
        assert isinstance(font_service.fonts_dir(), Path)
