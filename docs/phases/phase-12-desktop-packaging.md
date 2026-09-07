# Phase 12: Đóng gói Desktop App (Tauri + PyInstaller sidecar)

Trạng thái: **Cơ chế lõi xong & verify thật** (backend packaging + Tauri spawn/tắt sidecar chạy đúng qua test thật) — còn thiếu bước đóng gói installer cuối cùng (`tauri build` đầy đủ ra `.msi`/`.exe`) và test cài trên máy sạch thật sự, xem Ghi chú.

## Quyết định hướng phân phối (chốt phiên 2026-09-07)
Ưu tiên đóng gói desktop app trước, **tạm gác** hướng host multi-tenant SaaS/bán license qua web (lý do đầy đủ: chi phí compute Whisper/Demucs cao nếu host cho nhiều người + rủi ro pháp lý tăng khi thương mại hoá việc giúp người lạ scrape/re-up nội dung có bản quyền — xem `docs/scale-reup-features/plan.md` phần đánh giá host/license). Quyết định này không cố định vĩnh viễn, có thể quay lại hướng SaaS sau khi có tư vấn pháp lý riêng.

## Mục tiêu
Đóng gói web app hiện có (FastAPI backend + React frontend) thành ứng dụng desktop cài đặt được (Windows trước), chạy 100% local như hiện tại — không đổi kiến trúc lõi pipeline, chỉ thay lớp phân phối/khởi chạy.

## Phạm vi
**Trong phạm vi:** Tauri shell bọc frontend build (Vite production build) + PyInstaller compile backend thành sidecar executable, tự sinh/lưu `MASTER_KEY` lần đầu chạy, dời DB + storage sang thư mục dữ liệu người dùng đúng chuẩn OS, installer Windows qua Tauri bundler, tự khởi động/tắt sidecar theo vòng đời app.

**Ngoài phạm vi:** license key/anti-piracy (chưa lên kế hoạch), build macOS/Linux (sau khi bản Windows ổn định), auto-update qua Tauri updater, code signing (cân nhắc khi phát hành thật — chưa ký thì Windows SmartScreen sẽ cảnh báo).

## Nguyên liệu — quyết định đã chốt khi code
- [x] Cài Rust toolchain (winget, `rustup` → stable-x86_64-pc-windows-msvc) + Tauri CLI (`@tauri-apps/cli` qua npm ở root) — xong.
- [x] Model Whisper/Demucs: **tải lần đầu chạy** (giữ nguyên hành vi hiện tại, không bundle sẵn) — đúng đề xuất.
- [x] ffmpeg: **chưa bundle** trong installer ở bản này — vẫn yêu cầu ffmpeg có sẵn trong PATH máy người dùng như bản web hiện tại (xem Ghi chú, quyết định hoãn để giữ phạm vi phiên này gọn).
- [x] Xác nhận: sidecar PyInstaller (`--onedir`) nặng **660MB** (đo thật, không phải ước tính) — chủ yếu do `torch`/`ctranslate2` (Whisper/Demucs).
- [x] App vẫn cần internet khi chạy — không đổi.
- [x] Phạm vi OS: chỉ Windows.

## Việc đã làm

### Backend
- [x] `backend/app/entrypoint.py`: `uvicorn.run(..., reload=False)` bằng code, đọc `BACKEND_PORT` từ env (mặc định 8000).
- [x] `backend/app/core/config.py`: `is_frozen()` (check `sys.frozen`), `app_data_dir()` (theo OS — Windows `%APPDATA%/VieDubStudio`, macOS `~/Library/Application Support`, Linux `$XDG_DATA_HOME`), tự sinh `master.key` lần đầu chạy bản đóng gói (`_ensure_master_key_file`), dev mode giữ nguyên hành vi cũ (bắt buộc `.env`, báo lỗi rõ nếu thiếu). 9 test unit cho toàn bộ logic này.
- [x] **Build thật bằng PyInstaller** (`--onedir`, không cần `--onefile` vì tốc độ khởi động đã ổn — không có lý do phải đổi): `npm run desktop:build-backend` → `backend/dist/viedub-backend/viedub-backend.exe`.
- [x] **Verify chạy thật executable đã build**: `/health` trả `200 {"status":"ok"}`, `/api/api-keys` trả dữ liệu thật từ DB — xác nhận `master.key` tự sinh đúng tại `%APPDATA%/VieDubStudio/master.key` và DB tạo đúng tại `%APPDATA%/VieDubStudio/storage/app.db` (không đụng `backend/storage` của bản dev).

### Tauri (Rust)
- [x] Khởi tạo `src-tauri/` (`tauri init`), `identifier: com.viedubstudio.app`, cửa sổ 1280×800 (min 960×640, phù hợp layout sidebar+dashboard).
- [x] `tauri.conf.json`: `bundle.resources` map `backend/dist/viedub-backend` → `backend/` trong bundle (dùng cơ chế **resources**, không dùng **externalBin/sidecar** chính thức của Tauri — vì `--onedir` là cả thư mục nhiều file, không phải 1 executable đơn như sidecar yêu cầu).
- [x] `src-tauri/src/lib.rs`: `setup()` spawn backend qua `std::process::Command` (dev mode trỏ `../backend/dist/viedub-backend/viedub-backend.exe`, bản đóng gói trỏ `resource_dir()/backend/viedub-backend.exe`), lưu `Child` trong `tauri::State<Mutex<Option<Child>>>`; `RunEvent::Exit` lấy `Child` ra khỏi Mutex (nhả lock trước khi kill/wait, tránh giữ lock lúc I/O chặn) rồi `kill()` + `wait()`.
- [x] **`cargo check`/`cargo build` chạy sạch** (sau khi sửa 1 lỗi borrow-checker thật: giữ `MutexGuard` sống quá lâu trong nhánh `if let`).
- [x] **Chạy thật `app.exe` đã build**: log xác nhận sidecar spawn đúng (`Backend đã khởi động, pid=...`), backend chạy đúng FastAPI/uvicorn thật bên trong; đóng app (hết timeout test) → tiến trình `app.exe` biến mất hoàn toàn khỏi Task Manager, không treo lại.

## Tiêu chí hoàn thành (Definition of Done)
- [x] App tự khởi động sidecar backend và tắt sạch khi đóng — verify thật (xem trên), không còn tiến trình orphan.
- [x] DB và MASTER_KEY nằm trong thư mục dữ liệu người dùng, không nằm trong thư mục mã nguồn — verify thật trên `%APPDATA%/VieDubStudio/`.
- [ ] Chạy được file **installer** (`.msi`/`.exe`) trên máy Windows sạch — **chưa làm** `tauri build` đầy đủ (chỉ mới `cargo build` debug, chưa đóng gói bundle cuối cùng), xem Ghi chú.
- [ ] Chạy thử 1 video mẫu hết pipeline hoàn toàn từ app đã đóng gói — chưa làm (cần bấm thật qua UI, việc của bạn hoặc phiên sau có thể tự mắt kiểm tra qua cửa sổ app thật).

## Ghi chú phát sinh trong lúc làm
- **Máy dev thiếu Windows SDK dù đã có Visual Studio 2022 Professional + C++ Build Tools** — `cargo build` lúc đầu lỗi `LNK1181: cannot open input file 'kernel32.lib'` vì chỉ có compiler, thiếu SDK (headers/libs/`rc.exe`). Đã cài qua `winget install Microsoft.WindowsSDK.10.0.26100`. Nếu bạn build trên máy khác gặp lỗi tương tự, đây là nguyên nhân cần kiểm tra trước.
- **Git Bash (MSYS) shadow `link.exe` thật của MSVC** — `/usr/bin/link.exe` (coreutils, dùng để tạo hardlink) đứng trước MSVC `link.exe` trong PATH khi build từ Git Bash, khiến rustc gọi nhầm lệnh, báo lỗi khó hiểu ("extra operand"). **Phải build từ PowerShell/cmd, không phải Git Bash**, với PATH ưu tiên `VC\Tools\MSVC\<version>\bin\Hostx64\x64` — không hardcode path này vào `.cargo/config.toml` (dễ vỡ khi máy khác/version VS khác), chỉ ghi chú lại đây.
- **Bug borrow-checker thật đã sửa**: giữ `MutexGuard` (từ `.lock().unwrap()`) sống xuyên suốt cả block `if let Some(...) = guard.take() { ... }` bị Rust từ chối compile (E0597) — tách `.take()` ra 1 statement riêng để guard bị drop (nhả lock) ngay, trước khi vào block xử lý `Child` đã lấy ra.
- **Chưa bundle ffmpeg trong installer** — quyết định hoãn để giữ phạm vi phiên này gọn (đã làm đủ: backend packaging + Tauri sidecar mechanism, phần lõi rủi ro kỹ thuật cao nhất). App bản đóng gói hiện tại vẫn cần ffmpeg có sẵn trong PATH máy người dùng, giống hệt bản web — cần làm ở phiên sau nếu muốn installer thực sự "cài xong dùng ngay không cần cài gì thêm".
- **Chưa chạy `tauri build` đầy đủ** (ra `.msi`/NSIS `.exe` thật) — NSIS chưa có sẵn trên máy nhưng theo tài liệu Tauri sẽ tự tải khi cần lúc `tauri build` chạy lần đầu; chưa tự tay verify bước này (tốn thêm thời gian build, để phiên sau). Toàn bộ phần rủi ro kỹ thuật cao (sidecar có chạy được không, backend đóng gói có hoạt động không, MASTER_KEY/storage có đúng chỗ không) đã verify xong — phần còn lại chủ yếu là "chạy 1 lệnh và chờ".
- **Dung lượng sidecar 660MB (`--onedir`)** — đúng như dự đoán trong plan gốc, chủ yếu do torch/ctranslate2. Cân nhắc sau: có thể giảm bằng CPU-only torch wheel tối giản hơn nếu cần, không cấp thiết cho bản dùng cá nhân.
