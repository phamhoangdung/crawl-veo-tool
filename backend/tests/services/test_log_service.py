from pathlib import Path

from app.services import log_service


def test_missing_file_reports_not_exists(tmp_path: Path) -> None:
    tail = log_service.read_tail(10, path=tmp_path / "nope.log")
    assert tail.exists is False
    assert tail.lines == []


def test_returns_only_last_n_lines(tmp_path: Path) -> None:
    f = tmp_path / "b.log"
    f.write_text("\n".join(f"dòng {i}" for i in range(100)), encoding="utf-8")
    tail = log_service.read_tail(3, path=f)
    assert tail.lines == ["dòng 97", "dòng 98", "dòng 99"]


def test_big_file_drops_partial_first_line_and_keeps_utf8(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(log_service, "_TAIL_BYTES", 200)
    f = tmp_path / "big.log"
    f.write_text("\n".join(f"Đã tải video số {i}" for i in range(200)), encoding="utf-8")
    tail = log_service.read_tail(1000, path=f)
    assert tail.lines[-1] == "Đã tải video số 199"
    # Không dòng nào bị cắt cụt đầu: mọi dòng đều bắt đầu đúng "Đã tải".
    assert all(line.startswith("Đã tải video số ") for line in tail.lines)


def test_invalid_bytes_do_not_crash(tmp_path: Path) -> None:
    f = tmp_path / "bad.log"
    f.write_bytes(b"ok\n\xff\xfe broken\nend\n")
    tail = log_service.read_tail(10, path=f)
    assert tail.lines[0] == "ok"
    assert tail.lines[-1] == "end"
