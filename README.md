# Crawl Video Tool

Tool cá nhân chạy local: nhập từ khoá/chủ đề → crawl & tải video từ **Bilibili** (Douyin đang làm dở) → **dịch + lồng tiếng bằng AI** (Trung → Việt) → xuất video kèm **phụ đề song ngữ**, giữ nguyên nhạc nền gốc.

- **Backend**: Python 3.11+ / FastAPI / SQLAlchemy + SQLite (WAL) — chạy ở `:8000`
- **Frontend**: React + Vite + TypeScript + Tailwind + shadcn/ui — chạy ở `:5173`
- **Xử lý media**: ffmpeg, faster-whisper (STT), demucs (tách nhạc nền), edge-tts / ElevenLabs (TTS), OpenAI / Google (dịch)

> Tài liệu kiến trúc & roadmap chi tiết: [docs/overview/plan.md](docs/overview/plan.md) · Tiến độ từng phase: [docs/phases/](docs/phases/) · Quy ước code: [docs/conventions.md](docs/conventions.md)

---

## 1. Yêu cầu môi trường

| Công cụ | Ghi chú |
|---|---|
| **Python 3.11+** | Dùng `python3` (trên Windows lệnh `python` trần có thể trỏ tới stub của Microsoft Store) |
| **Node.js + npm** | Chỉ dùng để điều phối 2 service ở root |
| **pnpm** | `npm install -g pnpm` — `frontend/` dùng `pnpm-lock.yaml`, **không** dùng npm cho `frontend/` |
| **ffmpeg** | Bắt buộc, phải có trong PATH. Windows: `winget install --id Gyan.FFmpeg -e` · macOS: `brew install ffmpeg` · Linux: `apt install ffmpeg` |
| **git** | |

Sau khi cài ffmpeg trên Windows, **đóng và mở lại terminal/VSCode** — PATH mới chỉ áp dụng cho phiên mở sau đó.

## 2. Cài đặt

### 2.1. Cài tự động (khuyến nghị — chạy được trên cả 3 OS)

```bash
npm install     # cài concurrently cho root
npm run setup   # tạo venv + cài deps backend & frontend + tạo .env
```

[scripts/setup.mjs](scripts/setup.mjs) tự dò Python trong PATH, tạo `backend/.venv`, cài `requirements.txt`, chạy `pnpm install` cho frontend, tạo `.env` từ `.env.example` và cảnh báo nếu thiếu ffmpeg.

Muốn cài thẳng vào **Python global** (không tạo venv):

```bash
NO_VENV=1 npm run setup          # macOS / Linux
set NO_VENV=1 && npm run setup   # Windows cmd
$env:NO_VENV=1; npm run setup    # Windows PowerShell
```

Bước cài `faster-whisper` + `demucs` kéo theo PyTorch (~2GB) nên lần đầu có thể mất 5–15 phút tuỳ mạng.

### 2.2. Cài thủ công (nếu muốn tự kiểm soát)

```bash
cd backend
python3 -m venv .venv

# Windows
.venv\Scripts\python.exe -m pip install -r requirements.txt

# macOS / Linux
.venv/bin/python -m pip install -r requirements.txt

cd ../frontend && pnpm install
```

Lần chạy đầu tiên của pipeline sẽ tự tải thêm model về máy (cần mạng, hơi lâu):
`faster-whisper` (~vài trăm MB) và `demucs / htdemucs` (~80MB).

### 2.3. Biến môi trường

Chỉ có **một** file `.env` nguồn, đặt ở root (`npm run setup` đã tạo sẵn; nếu cài tay thì `cp .env.example .env`).

Mở `.env` và điền `MASTER_KEY` — khoá dùng để mã hoá các API key của provider lưu trong DB. Sinh giá trị mới:

```bash
python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

| Biến | Bắt buộc | Mặc định |
|---|---|---|
| `MASTER_KEY` | ✅ | — |
| `BACKEND_PORT` | | `8000` |
| `FRONTEND_PORT` | | `5173` |
| `DATABASE_URL` | | `sqlite:///backend/storage/app.db` |

`backend/.env` và `frontend/.env` được **sinh tự động** từ file này mỗi lần chạy `npm run dev` (script [scripts/sync-env.mjs](scripts/sync-env.mjs)) — đừng sửa tay 2 file đó.

API key của các nhà cung cấp AI (OpenAI, Google, ElevenLabs...) **không** nằm trong `.env` — nhập trực tiếp trong UI ở trang **API Keys**, tool sẽ mã hoá bằng `MASTER_KEY` rồi lưu vào DB.

## 3. Chạy dự án

```bash
npm run dev    # chạy song song backend (:8000) + frontend (:5173)
```

Mở http://localhost:5173. Lệnh này chạy như nhau trên Windows, macOS và Linux.

**Backend dùng Python nào?** [scripts/run-backend.mjs](scripts/run-backend.mjs) dò theo thứ tự:

1. Biến môi trường `PYTHON` nếu có — `PYTHON=/đường/dẫn/python npm run dev`
2. `backend/.venv` — tự chọn `Scripts/python.exe` (Windows) hay `bin/python` (macOS/Linux)
3. Python global trong PATH — `python` trên Windows, `python3` trên macOS/Linux

Nhờ vậy dự án chạy được cả khi có venv lẫn khi bạn muốn dùng Python global, không cần sửa `package.json`.

### Kiểm tra đã chạy đúng

```bash
curl http://localhost:8000/health              # backend sống
curl http://localhost:8000/health/downloader   # API Bilibili còn hoạt động đúng như code giả định
```

API docs (Swagger) tự động ở http://localhost:8000/docs.

## 4. Luồng sử dụng

1. **Trending / Crawl** — chọn chủ đề hoặc nhập từ khoá, tool lấy danh sách video từ Bilibili (có xem trước chi phí AI ước tính trước khi chạy).
2. **Download** — tải video gốc, không watermark.
3. **Transcribe** — faster-whisper bóc lời thoại tiếng Trung kèm timestamp (có thể sửa tay transcript trong UI).
4. **Translate** — dịch sang tiếng Việt qua provider đã chọn.
5. **Dub** — demucs tách giọng khỏi nhạc nền, TTS đọc bản dịch, ghép lại **giữ nguyên nhạc nền gốc** (có time-stretch cho khớp timing).
6. **Subtitles** — xuất `.srt` song ngữ, tuỳ chọn burn-in vào video.
7. **Library** — xem lại, tải từng video hoặc tải hàng loạt dạng `.zip`.

## 5. Cấu trúc thư mục

```
backend/
  app/
    api/          # FastAPI routers (health, crawl, trending, api_keys, pipeline, library)
    services/     # business logic (download, transcribe, translate, tts, dubbing, subtitle, cost...)
    adapters/     # tích hợp bên ngoài: bilibili, douyin, translate/*, tts/*, ffmpeg, demucs
    models/       # SQLAlchemy models
    schemas/      # Pydantic schemas
    core/         # config, db, security (mã hoá API key)
  storage/        # DB + file media sinh ra (gitignored)
frontend/
  src/
    features/     # crawl, trending, library, api-keys, settings, dashboard...
    routes/       # TanStack Router (file-based)
    components/   # shadcn/ui + layout dùng chung
scripts/sync-env.mjs
docs/
  overview/plan.md   # kiến trúc tổng thể
  phases/            # checklist thực thi từng phase
  conventions.md     # quy ước code
```

## 6. API chính

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/health`, `/health/downloader` | Health check |
| `GET` | `/api/trending/bilibili/categories\|popular\|ranking` | Khám phá trending |
| `POST` | `/api/jobs` | Tạo job crawl |
| `POST` | `/api/jobs/{job_id}/cost-estimate` | Ước tính chi phí AI |
| `GET/PUT` | `/api/api-keys` | Quản lý API key provider |
| `GET` | `/api/videos/{id}` | Chi tiết video |
| `POST` | `/api/videos/{id}/download\|transcribe\|translate\|dub\|burn-subtitles` | Các bước pipeline |
| `PUT` | `/api/videos/{id}/transcript` | Sửa transcript thủ công |
| `GET` | `/api/videos/{id}/subtitles.srt` | Tải phụ đề |
| `GET` | `/api/library`, `/api/library/{id}/download`, `/api/library/download-zip` | Thư viện & tải về |

## 7. Test & lint

```bash
npm test               # chạy cả backend (pytest) lẫn frontend (vitest)
npm run test:backend   # chỉ backend — tự dò Python như khi chạy dev
npm run test:frontend  # chỉ frontend

pnpm -C frontend lint
pnpm -C frontend format
```

Cần chạy 1 lệnh Python bất kỳ bằng đúng interpreter của dự án:

```bash
node scripts/run-python.mjs -m pytest backend/tests/test_subtitle.py
```

## 8. Sự cố thường gặp

- **`ffmpeg: command not found` dù đã cài** → PATH chỉ cập nhật cho terminal mới; đóng mở lại terminal/VSCode.
- **`WinError 10013` khi `npm run dev`** → cổng 8000 còn bị tiến trình cũ giữ (uvicorn `--reload` không thay hẳn worker). Tìm và tắt:
  ```powershell
  Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'multiprocessing-fork' }
  Stop-Process -Id <id> -Force
  ```
- **`UNIQUE constraint failed` / `no such column` sau khi đổi model** → dự án MVP chưa dùng Alembic, schema không tự migrate. Xoá `backend/storage/app.db*` để SQLAlchemy tạo lại (mất dữ liệu test cũ), hoặc `ALTER TABLE` thủ công.
- **CORS bị chặn** → Vite tự nhảy cổng (5174, 5175...) nếu 5173 bận. Backend đã chấp nhận mọi cổng `localhost`; nếu vẫn lỗi, kiểm tra `CORSMiddleware` trong [backend/app/main.py](backend/app/main.py).
- **Lần chạy pipeline đầu tiên rất lâu** → đang tải model faster-whisper / demucs, chỉ chậm 1 lần.
- **`npm run setup` / `npm run dev` đứng im không in gì** → bản Python trong PATH bị hỏng (ngay cả `python3 --version` cũng treo). Script có timeout 10s và sẽ báo lỗi, nhưng cách sửa là cài lại Python rồi trỏ vào bản mới:
  ```bash
  python3 --version          # nếu lệnh này treo → Python hỏng
  brew reinstall python@3.12 # macOS
  PYTHON=python3.12 npm run setup
  ```
- **pip lỗi khi cài `demucs` / `faster-whisper`** → PyTorch chưa hỗ trợ phiên bản Python đang dùng (hay gặp với 3.13+). Dùng Python 3.11 hoặc 3.12: `PYTHON=python3.12 npm run setup`.

Hướng dẫn cài chi tiết riêng cho Windows: [SETUP.md](SETUP.md).

## 9. Trạng thái

| Phase | Trạng thái |
|---|---|
| 0. Scaffolding | Hoàn thành |
| 1. Crawl & trending (Bilibili) | Xong (trừ batch queue concurrency) |
| 2. AI pipeline MVP | Xong, đã verify end-to-end |
| 3. Multi-provider + Douyin | Một phần — cost estimate xong, Douyin cần cookie thật để test |
| 4. Audio quality (tách nhạc nền) | Lõi xong — chunking video dài chưa làm |
| 5. Phụ đề song ngữ + Thư viện | Xong & đã verify |
| 6. Hardening & Ops | Phần cốt lõi xong (storage cleanup, health-check, SETUP.md) |
| 7. Đóng gói để bán | Chưa lên kế hoạch |

Tool dùng cá nhân, chưa có xác thực người dùng thật — **đừng expose ra internet**.
