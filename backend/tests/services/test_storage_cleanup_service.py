import os
import time
from unittest.mock import patch

from app.services import storage_cleanup_service


def test_cleanup_removes_only_old_numeric_job_folders(tmp_path):
    old_job = tmp_path / "1"
    old_job.mkdir()
    (old_job / "video.mp4").write_bytes(b"x")

    new_job = tmp_path / "2"
    new_job.mkdir()

    not_a_job = tmp_path / "_zips"
    not_a_job.mkdir()

    old_time = time.time() - 40 * 86400
    os.utime(old_job, (old_time, old_time))

    with patch("app.services.storage_cleanup_service._STORAGE_ROOT", tmp_path):
        removed = storage_cleanup_service.cleanup_old_job_folders(max_age_days=30)

    assert removed == ["1"]
    assert not old_job.exists()
    assert new_job.exists()
    assert not_a_job.exists()


def test_get_storage_usage_bytes_sums_file_sizes(tmp_path):
    (tmp_path / "1").mkdir()
    (tmp_path / "1" / "a.mp4").write_bytes(b"12345")
    (tmp_path / "1" / "b.mp4").write_bytes(b"12")

    with patch("app.services.storage_cleanup_service._STORAGE_ROOT", tmp_path):
        assert storage_cleanup_service.get_storage_usage_bytes() == 7
