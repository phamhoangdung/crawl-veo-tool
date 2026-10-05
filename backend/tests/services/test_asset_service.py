import pytest

from app.services import asset_service

PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d4944415478da63f8cf0000030101002d0d0aeb0000000049454e44ae426082"
)


@pytest.fixture(autouse=True)
def temp_assets_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Do not touch the real storage — the test creates/deletes files so it must be isolated."""
    monkeypatch.setattr(asset_service, "storage_dir", lambda: tmp_path)
    return tmp_path


class TestDetectKind:
    """Classify by use: an intro .mp4 goes into the video track, a logo .png into the image track."""

    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("logo.png", "image"),
            ("LOGO.PNG", "image"),
            ("anh.jpeg", "image"),
            ("intro.mp4", "video"),
            ("outro.MOV", "video"),
            ("nhac.mp3", "audio"),
            ("nhac.wav", "audio"),
        ],
    )
    def test_maps_extension_to_kind(self, filename: str, expected: str) -> None:
        assert asset_service.detect_kind(filename) == expected

    def test_rejects_unknown_extension(self) -> None:
        with pytest.raises(asset_service.AssetError, match="không hỗ trợ"):
            asset_service.detect_kind("script.exe")

    def test_rejects_file_without_extension(self) -> None:
        with pytest.raises(asset_service.AssetError):
            asset_service.detect_kind("noextension")


class TestSafeName:
    def test_strips_vietnamese_accents(self) -> None:
        """ffmpeg filter_complex handles non-ASCII paths unreliably."""
        asset = asset_service.save_asset("Logo Kênh Của Tôi.png", PNG_1X1)

        assert asset.name == "Logo_Kenh_Cua_Toi.png"
        assert asset.name.isascii()

    def test_strips_path_traversal(self) -> None:
        """The file name must not escape the assets directory."""
        asset = asset_service.save_asset("../../etc/passwd.png", PNG_1X1)

        assert "/" not in asset.name
        assert ".." not in asset.name

    def test_quotes_removed(self) -> None:
        """A single quote breaks the ffmpeg filter syntax."""
        asset = asset_service.save_asset("my'logo\".png", PNG_1X1)

        assert "'" not in asset.name
        assert '"' not in asset.name


class TestSaveAsset:
    def test_saves_file_to_disk(self, temp_assets_dir) -> None:
        asset = asset_service.save_asset("logo.png", PNG_1X1)

        from pathlib import Path

        assert Path(asset.path).read_bytes() == PNG_1X1
        assert asset.size == len(PNG_1X1)
        assert asset.kind == "image"

    def test_same_name_twice_does_not_overwrite(self) -> None:
        """Users often have several versions of 'logo.png' — they must not overwrite each other."""
        first = asset_service.save_asset("logo.png", PNG_1X1)
        second = asset_service.save_asset("logo.png", PNG_1X1 + b"\x00")

        assert first.id != second.id
        assert first.path != second.path
        assert len(asset_service.list_assets()) == 2

    def test_rejects_empty_file(self) -> None:
        with pytest.raises(asset_service.AssetError, match="rỗng"):
            asset_service.save_asset("logo.png", b"")

    def test_rejects_oversized_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(asset_service.MAX_BYTES, "image", 10)

        with pytest.raises(asset_service.AssetError, match="vượt giới hạn"):
            asset_service.save_asset("logo.png", PNG_1X1)


class TestListAndDelete:
    def test_filters_by_kind(self) -> None:
        asset_service.save_asset("logo.png", PNG_1X1)
        asset_service.save_asset("nhac.mp3", b"ID3fake")

        assert [a.kind for a in asset_service.list_assets("image")] == ["image"]
        assert [a.kind for a in asset_service.list_assets("audio")] == ["audio"]
        assert len(asset_service.list_assets()) == 2

    def test_ignores_unrelated_files_in_dir(self, temp_assets_dir) -> None:
        """A stray file in the directory (copied by hand by the user) must not break the list."""
        asset_service.assets_dir()
        (temp_assets_dir / "assets" / "khong-dung-quy-uoc.png").write_bytes(PNG_1X1)
        asset_service.save_asset("logo.png", PNG_1X1)

        assert len(asset_service.list_assets()) == 1

    def test_delete_removes_file(self) -> None:
        asset = asset_service.save_asset("logo.png", PNG_1X1)

        assert asset_service.delete_asset(asset.id) is True
        assert asset_service.get_asset(asset.id) is None

    def test_delete_missing_returns_false(self) -> None:
        assert asset_service.delete_asset("khongtontai") is False


class TestImportFromPath:
    def test_copies_existing_file(self, tmp_path) -> None:
        source = tmp_path / "intro.mp4"
        source.write_bytes(b"fake video")

        asset = asset_service.import_from_path(str(source))

        assert asset.kind == "video"
        # The source file must remain intact — users must not lose their files.
        assert source.exists()
        assert asset_service.get_asset(asset.id) is not None

    def test_rejects_missing_file(self) -> None:
        with pytest.raises(asset_service.AssetError, match="Không tìm thấy"):
            asset_service.import_from_path("/khong/ton/tai.mp4")

    def test_rejects_directory(self, tmp_path) -> None:
        with pytest.raises(asset_service.AssetError):
            asset_service.import_from_path(str(tmp_path))
