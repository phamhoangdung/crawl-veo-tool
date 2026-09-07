from pathlib import Path

import pytest

from app.core import config


class TestIsFrozen:
    def test_false_in_normal_dev_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delattr("sys.frozen", raising=False)
        assert config.is_frozen() is False

    def test_true_when_pyinstaller_sets_frozen_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.frozen", True, raising=False)
        assert config.is_frozen() is True


class TestAppDataDir:
    def test_windows_uses_appdata_env_var(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(config.sys, "platform", "win32")
        monkeypatch.setenv("APPDATA", str(tmp_path))
        result = config.app_data_dir()
        assert result == tmp_path / "VieDubStudio"

    def test_macos_uses_application_support(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config.sys, "platform", "darwin")
        result = config.app_data_dir()
        assert result == Path.home() / "Library" / "Application Support" / "VieDubStudio"


class TestEnsureMasterKeyFile:
    def test_generates_and_persists_a_new_key(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(config, "app_data_dir", lambda: tmp_path)

        key = config._ensure_master_key_file()

        assert key
        key_file = tmp_path / "master.key"
        assert key_file.exists()
        assert key_file.read_text(encoding="utf-8").strip() == key

    def test_reuses_existing_key_on_second_call(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(config, "app_data_dir", lambda: tmp_path)

        first = config._ensure_master_key_file()
        second = config._ensure_master_key_file()

        assert first == second

    def test_generated_key_is_a_valid_fernet_key(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from cryptography.fernet import Fernet

        monkeypatch.setattr(config, "app_data_dir", lambda: tmp_path)
        key = config._ensure_master_key_file()

        # Không raise là đủ verify key hợp lệ cho Fernet.
        fernet = Fernet(key.encode())
        token = fernet.encrypt(b"hello")
        assert fernet.decrypt(token) == b"hello"


class TestDefaultMasterKey:
    def test_raises_clear_error_when_not_frozen_and_unconfigured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "is_frozen", lambda: False)
        with pytest.raises(RuntimeError, match="MASTER_KEY"):
            config._default_master_key()

    def test_auto_generates_when_frozen(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(config, "is_frozen", lambda: True)
        monkeypatch.setattr(config, "app_data_dir", lambda: tmp_path)

        key = config._default_master_key()

        assert key
        assert (tmp_path / "master.key").exists()
