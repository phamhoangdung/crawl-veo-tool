# Cài đặt trên Windows

Hướng dẫn cài lại toàn bộ dự án từ đầu trên 1 máy Windows mới, dựa trên những gì đã gặp thật khi build dự án này (xem thêm chi tiết/lý do ở từng `docs/phases/phase-N-*.md`).

## 1. Cài công cụ nền tảng
- **Python 3.11+** — kiểm tra `python3 --version` (trên Windows, lệnh `python` trần có thể trỏ tới Python 2 hoặc App Store stub, luôn dùng `python3` hoặc gọi thẳng venv).
- **Node.js** (kèm npm) — dùng cho điều phối script ở root.
- **pnpm** — `npm install -g pnpm` (frontend dùng `pnpm-lock.yaml`, không dùng npm cho `frontend/`).
- **ffmpeg** — cài qua winget: `winget install --id Gyan.FFmpeg -e`. Sau khi cài, **đóng và mở lại terminal/VSCode** — PATH mới chỉ áp dụng cho phiên/terminal mở sau đó, phiên đang mở sẽ không tự thấy lệnh `ffmpeg`.
- **git**.

## 2. Backend

```bash
cd backend
python3 -m venv .venv
./.venv/Scripts/pip.exe install -r requirements.txt
```

Lần đầu chạy sẽ tự tải thêm: model `faster-whisper` (~small, vài trăm MB), model `demucs` (htdemucs, ~80MB) — cần mạng, hơi chậm lần đầu.

## 3. Frontend

```bash
cd frontend
pnpm install
```

## 4. Cấu hình env

```bash
cp .env.example .env   # ở root
```

Mở `.env` vừa tạo, điền `MASTER_KEY` (dùng để mã hoá API key lưu trong DB) — sinh 1 giá trị mới bằng:

```bash
python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

## 5. Chạy dự án

Từ root:

```bash
npm install   # 1 lần đầu — cài concurrently để điều phối 2 service
npm run dev   # chạy cả backend (:8000) và frontend (:5173) cùng lúc
```

`predev` sẽ tự đồng bộ `.env` gốc vào `backend/.env` và `frontend/.env` mỗi lần chạy — không sửa tay 2 file đó.

## 6. Kiểm tra đã cài đúng

```bash
curl http://localhost:8000/health              # backend sống
curl http://localhost:8000/health/downloader   # Bilibili API còn hoạt động đúng như code giả định
```

Mở `http://localhost:5173` trên trình duyệt — nếu thấy trang Dashboard là frontend đã chạy đúng.

## Vướng mắc thường gặp (đã gặp thật khi build)
- **`ffmpeg: command not found` dù đã cài** → do PATH chỉ cập nhật cho terminal mới, đóng mở lại terminal/VSCode.
- **Backend lỗi `WinError 10013` khi chạy `npm run dev`** → cổng 8000 đang bị giữ bởi 1 tiến trình cũ chưa tắt hẳn (thường do `uvicorn --reload` không thay hẳn worker process khi code đổi). Tìm đúng process con bằng PowerShell rồi tắt: `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'multiprocessing-fork' }`, sau đó `Stop-Process -Id <id> -Force`.
- **Lỗi `UNIQUE constraint failed` hoặc `no such column` sau khi đổi model** → dự án MVP chưa dùng Alembic, schema DB không tự migrate. Xoá `backend/storage/app.db*` để SQLAlchemy tạo lại từ đầu (mất dữ liệu test cũ), hoặc tự `ALTER TABLE` thủ công nếu muốn giữ dữ liệu.
- **CORS bị chặn dù backend chạy đúng** → Vite tự đổi cổng (5174, 5175...) nếu 5173 đang bận; backend đã cấu hình chấp nhận mọi cổng `localhost` nên việc này không còn xảy ra, nhưng nếu gặp lại thì kiểm tra `backend/app/main.py` phần `CORSMiddleware`.
