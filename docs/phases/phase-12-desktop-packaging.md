# Phase 12: Đóng gói Desktop App (Tauri + PyInstaller sidecar)

Trạng thái: Chưa bắt đầu — plan sẵn sàng.

## Quyết định hướng phân phối (chốt phiên 2026-09-07)
Ưu tiên đóng gói desktop app trước, **tạm gác** hướng host multi-tenant SaaS/bán license qua web (lý do đầy đủ: chi phí compute Whisper/Demucs cao nếu host cho nhiều người + rủi ro pháp lý tăng khi thương mại hoá việc giúp người lạ scrape/re-up nội dung có bản quyền — xem `docs/scale-reup-features/plan.md` phần đánh giá host/license). Quyết định này không cố định vĩnh viễn, có thể quay lại hướng SaaS sau khi có tư vấn pháp lý riêng.

## Mục tiêu
Đóng gói web app hiện có (FastAPI backend + React frontend) thành ứng dụng desktop cài đặt được (Windows trước), chạy 100% local như hiện tại — không đổi kiến trúc lõi pipeline, chỉ thay lớp phân phối/khởi chạy.

## Phạm vi
**Trong phạm vi:** Tauri shell bọc frontend build (Vite production build) + PyInstaller compile backend thành sidecar executable, tự sinh/lưu `MASTER_KEY` lần đầu chạy, dời DB + storage sang thư mục dữ liệu người dùng đúng chuẩn OS, installer Windows qua Tauri bundler, tự khởi động/tắt sidecar theo vòng đời app.

**Ngoài phạm vi:** license key/anti-piracy (Phase 13 riêng, chưa lên kế hoạch), build macOS/Linux (sau khi bản Windows ổn định), auto-update qua Tauri updater, code signing (cân nhắc khi phát hành thật — chưa ký thì Windows SmartScreen sẽ cảnh báo).

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [ ] Cài Rust toolchain + Tauri CLI trên máy dev (chưa có trong repo hiện tại).
- [ ] Quyết định: model Whisper/Demucs bundle sẵn trong installer hay tải lần đầu chạy (download-on-first-run)? Đề xuất tải lần đầu chạy — installer nhỏ hơn, khớp cách Demucs đã tự tải model hiện tại (ghi chú Phase 4: model `htdemucs` ~80MB tự tải lần đầu).
- [ ] Quyết định: bundle sẵn ffmpeg trong installer (khuyến nghị — ổn định, không phụ thuộc mạng lúc cần dùng ngay) hay tải lần đầu chạy?
- [ ] **Cần biết trước**: `demucs` kéo theo `torch`/`torchaudio` — PyInstaller bundle sidecar sẽ khá nặng (ước tính có thể 1-2GB+ tuỳ bản CPU-only của torch, cần đo thật sau khi build thử). Không chặn kế hoạch, nhưng ảnh hưởng trực tiếp dung lượng file cài đặt cuối cùng.
- [ ] Xác nhận: app desktop **vẫn cần internet khi chạy** (gọi API dịch/TTS/crawl Bilibili-Douyin) — không phải app offline hoàn toàn, chỉ Whisper/Demucs/ffmpeg chạy local.
- [ ] Xác nhận phạm vi OS: chỉ Windows cho bản đầu (khớp máy dev hiện tại)?

## Việc cần làm
- [ ] `backend/app/entrypoint.py` (mới): gọi `uvicorn.run(app, host="127.0.0.1", port=..., reload=False)` trực tiếp bằng code — không qua CLI `--reload` như `scripts/run-backend.mjs` hiện tại, vì reload mode dùng subprocess watcher không tương thích PyInstaller.
- [ ] `backend/app/core/config.py`: đổi `DEFAULT_DB_PATH`/storage path — khi chạy dạng đóng gói (detect `sys.frozen` của PyInstaller hoặc biến môi trường riêng) trỏ vào thư mục dữ liệu người dùng chuẩn OS (`%APPDATA%/VieDubStudio` trên Windows) thay vì `backend/storage` cạnh mã nguồn như bản dev.
- [ ] Cơ chế tự sinh `MASTER_KEY` lần đầu chạy nếu chưa có file cấu hình trong thư mục dữ liệu người dùng — thay cho yêu cầu tự điền `.env` như bản dev hiện tại (`docs/phases/phase-0-scaffolding.md`).
- [ ] Build thử PyInstaller: `pyinstaller --onefile backend/app/entrypoint.py` và so sánh với `--onedir` (đo thời gian khởi động thật — `--onefile` giải nén lại torch/ctranslate2 mỗi lần mở có thể chậm) để chọn.
- [ ] Khởi tạo dự án Tauri (`src-tauri/`), cấu hình `tauri.conf.json` trỏ `frontendDist` vào `frontend/dist` (Vite build) và khai báo sidecar trỏ executable PyInstaller vừa build.
- [ ] `src-tauri/src/main.rs`: spawn sidecar khi app khởi động, poll endpoint `/health` đã có sẵn (`app/api/health.py`) tới khi backend sẵn sàng rồi mới hiện cửa sổ chính; kill sidecar khi đóng app (tránh tiến trình Python orphan chạy nền).
- [ ] `frontend`: rà lại các chỗ gọi API có giả định "đang chạy qua Vite dev server" (proxy/base URL), đảm bảo hoạt động đúng trong context Tauri webview.
- [ ] Cấu hình Tauri bundler tạo installer Windows (`.msi`/NSIS `.exe`).
- [ ] Test tay: cài trên máy Windows sạch (không có Python/Node/ffmpeg cài sẵn) → mở app → chạy thử 1 job crawl → dịch → lồng tiếng đầy đủ, xác nhận không phụ thuộc gì ngoài installer.

## Tiêu chí hoàn thành (Definition of Done)
- [ ] Chạy được installer trên máy Windows sạch, cài xong mở lên được giao diện.
- [ ] Chạy thử 1 video mẫu hết pipeline (crawl → transcribe → translate → dub) hoàn toàn từ app đã đóng gói, không cần mở terminal.
- [ ] Đóng app tắt sạch sidecar backend — kiểm tra Task Manager không còn tiến trình Python treo lại.
- [ ] DB và file output nằm trong thư mục dữ liệu người dùng (không nằm trong thư mục cài đặt app) — để gỡ cài đặt không tự xoá dữ liệu người dùng, cài lại không lỗi quyền ghi.

## Ghi chú phát sinh trong lúc làm
(Điền khi bắt đầu code.)
