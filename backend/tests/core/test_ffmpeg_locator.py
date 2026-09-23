import os
import sys
from pathlib import Path

import pytest

from app.core import ffmpeg_locator

EXE = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """PATH rỗng (không thấy ffmpeg thật của máy dev) + không có nơi cài nào."""
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(ffmpeg_locator, "_registry_path_dirs", lambda: [])
    monkeypatch.setattr(ffmpeg_locator, "_known_install_dirs", lambda: [])


def _fake_ffmpeg(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    exe = directory / EXE
    exe.write_bytes(b"")
    exe.chmod(0o755)
    return directory


def test_returns_false_when_ffmpeg_nowhere(clean_env) -> None:
    assert ffmpeg_locator.ensure_ffmpeg_on_path() is False


def test_finds_ffmpeg_in_registry_dir_and_adds_to_path(clean_env, monkeypatch, tmp_path) -> None:
    user_dir = _fake_ffmpeg(tmp_path / "user-bin")
    monkeypatch.setattr(ffmpeg_locator, "_registry_path_dirs", lambda: [user_dir])

    assert ffmpeg_locator.ensure_ffmpeg_on_path() is True
    assert os.environ["PATH"].startswith(str(user_dir))


def test_finds_ffmpeg_in_known_install_dir(clean_env, monkeypatch, tmp_path) -> None:
    known = _fake_ffmpeg(tmp_path / "winget-links")
    monkeypatch.setattr(ffmpeg_locator, "_known_install_dirs", lambda: [known])
    assert ffmpeg_locator.ensure_ffmpeg_on_path() is True


def test_idempotent_does_not_duplicate_path_entry(clean_env, monkeypatch, tmp_path) -> None:
    user_dir = _fake_ffmpeg(tmp_path / "user-bin")
    monkeypatch.setattr(ffmpeg_locator, "_registry_path_dirs", lambda: [user_dir])
    ffmpeg_locator.ensure_ffmpeg_on_path()
    before = os.environ["PATH"]
    assert ffmpeg_locator.ensure_ffmpeg_on_path() is True
    assert os.environ["PATH"] == before


def test_ensure_ffmpeg_available_raises_only_when_truly_missing(clean_env) -> None:
    from app.adapters import ffmpeg

    with pytest.raises(ffmpeg.FfmpegNotFoundError):
        ffmpeg.ensure_ffmpeg_available()


def test_real_registry_lookup_does_not_crash() -> None:
    """Gọi thật (không mock) — chỉ cần trả về danh sách hợp lệ, không nổ."""
    assert isinstance(ffmpeg_locator._registry_path_dirs(), list)
    assert isinstance(ffmpeg_locator.find_ffmpeg_dir(), (Path, type(None)))
