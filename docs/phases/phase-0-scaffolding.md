# Phase 0: Scaffolding (khung backend + frontend)

Trạng thái: **Hoàn thành** (khung chạy được, xem Ghi chú bên dưới)

## Mục tiêu
Dựng khung backend + frontend rỗng, DB schema nền tảng, cơ chế bảo mật API key. Chưa có tính năng nghiệp vụ (crawl/AI) nào chạy thật — mục tiêu là 2 phía backend/frontend nói chuyện được và schema DB đúng từ đầu để các phase sau không phải migrate lại.

## Phạm vi
**Trong phạm vi:**
- Backend FastAPI project skeleton.
- SQLite + SQLAlchemy, bật `PRAGMA journal_mode=WAL`.
- DB schema v0 với field `user_id`/`workspace_id` sẵn từ đầu (xem lý do ở docs/overview/plan.md phần "Đã chốt về mô hình sử dụng"): `users`, `api_keys` (encrypted), `jobs` (status enum theo state machine), `videos`.
- State machine cho job: `queued → downloading → downloaded → separating_audio → transcribing → translating → dubbing → muxing → done / failed_at_<step>`.
- Cơ chế mã hoá API key (Fernet + master key từ env).
- Clone template [satnaing/shadcn-admin](https://github.com/satnaing/shadcn-admin), dọn trang mẫu không cần, đổi branding tối thiểu.
- 1 API `/health` + frontend gọi thử để xác nhận kết nối.

**Ngoài phạm vi:** chưa crawl thật, chưa gọi AI provider thật, chưa có form nghiệp vụ thật.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [x] Python 3.11+ đã cài trên máy (3.11.9 xác nhận).
- [x] Node.js đã cài (v24.15.0 xác nhận, kèm pnpm 10.33.2 — template dùng pnpm-lock.yaml nên cài bằng pnpm thay vì npm).
- [ ] ffmpeg binary cài sẵn và có trong PATH — **chưa có trên máy, không chặn Phase 0 nhưng bắt buộc phải cài trước khi vào Phase 1** (cần để merge DASH stream Bilibili).
- [x] Generate `MASTER_KEY` (Fernet key), lưu ở `backend/.env` (gitignored) + `backend/.env.example` (placeholder, commit được).
- [x] Cấu trúc thư mục gốc: `backend/` + `frontend/`.

## Việc cần làm
- [x] Tạo `backend/` với FastAPI skeleton (`requirements.txt`, cấu trúc `app/api`, `app/models`, `app/core`; `app/adapters` để trống, tạo ở Phase 1 khi có adapter đầu tiên — tránh tạo thư mục rỗng không cần thiết).
- [x] SQLAlchemy models: `User`, `ApiKey`, `Job` (enum `Platform`, `JobStatus`), `Video` (enum `VideoStatus` đủ các bước + `failed_<step>` theo state machine trong plan).
- [x] Bật WAL mode khi khởi tạo DB (xác nhận qua `PRAGMA journal_mode` = `wal`).
- [x] Module mã hoá/giải mã API key (Fernet) đọc `MASTER_KEY` từ env (`app/core/security.py`) + hàm `mask_secret()`.
- [x] Clone shadcn-admin vào `frontend/`, gỡ `.git` lồng để hợp nhất vào repo chính.
- [x] Thêm route `/health` ở backend, xác nhận bằng `curl` (chưa wire vào 1 trang UI cụ thể — để làm cùng lúc khi dựng trang thật ở Phase 1, tránh code UI tạm thời rồi xoá).
- [x] `git init` cho project (chưa commit — để bạn tự quyết định thời điểm commit đầu tiên).

## Tiêu chí hoàn thành (Definition of Done)
- [x] Chạy **`npm run dev` từ root** khởi động cả backend (port 8000) lẫn frontend (port 5173) cùng lúc, cả hai trả về HTTP OK.
- [x] DB tạo ra file `.db` đúng schema: bảng `users`, `api_keys`, `jobs`, `videos` đều có mặt, `user_id` có ở `api_keys`/`jobs`/`videos`.
- [x] Script test lưu + đọc lại 1 API key mã hoá thành công (roundtrip đúng, giá trị mã hoá khác plaintext, mask hiển thị đúng).
- [ ] Frontend gọi `/health` thật từ 1 trang UI — dời sang đầu Phase 1 (xem ghi chú dưới), vì cần 1 trang thật để gọi thay vì viết code tạm. Đã có sẵn `VITE_API_BASE_URL` (env) để dùng khi làm.

## Cách chạy dự án
Root có `.env` (copy từ `.env.example`, điền `MASTER_KEY`) làm **nguồn duy nhất** — mỗi lần `npm run dev`, bước `predev` tự chạy `scripts/sync-env.mjs` để sinh lại `backend/.env` (MASTER_KEY, DATABASE_URL nếu có override) và `frontend/.env` (`VITE_API_BASE_URL`). Không sửa tay `backend/.env`/`frontend/.env` — sửa ở root `.env` rồi chạy lại.

```bash
npm install       # 1 lần đầu — cài concurrently ở root
npm run dev        # chạy cả backend (:8000) + frontend (:5173) từ root
```

Lưu ý 2 package manager khác nhau trong repo: **npm** ở root (chỉ để điều phối script), **pnpm** trong `frontend/` (vì template có `pnpm-lock.yaml`) — không tự ý đổi lẫn giữa 2 loại lockfile.

## Ghi chú phát sinh trong lúc làm
- **Bug đã sửa**: `app/core/config.py` ban đầu load `.env` và default `DATABASE_URL` theo đường dẫn tương đối (phụ thuộc CWD của process) — chạy `uvicorn` từ root (qua `--app-dir backend`) bị lỗi thiếu `MASTER_KEY` vì không tìm thấy `.env`. Đã sửa để cả 2 đều neo theo vị trí file `config.py` (`Path(__file__).resolve()`), không phụ thuộc CWD — giờ chạy từ root hay từ `backend/` đều load đúng.
- ~~Trên Windows, npm chạy script bằng `cmd.exe` — path executable trong `package.json` scripts phải dùng backslash (`backend\.venv\Scripts\python.exe`), dùng forward-slash sẽ bị lỗi "not recognized as an internal or external command".~~ **Đã thay thế**: `package.json` không còn hardcode path Python nữa. `dev:backend` gọi [scripts/run-backend.mjs](../../scripts/run-backend.mjs) — dò `PYTHON` env → `backend/.venv` (tự phân biệt `Scripts/` vs `bin/`) → Python global trong PATH. Nhờ đó chạy được trên Windows/macOS/Linux và cả khi không dùng venv. Logic dò dùng chung ở [scripts/python-path.mjs](../../scripts/python-path.mjs).
- ~~Template shadcn-admin có sẵn `@clerk/react`~~ **Đã gỡ** (trong lúc làm Phase 1): xoá `src/routes/clerk/`, `src/assets/clerk-*.tsx`, dependency `@clerk/react`, mục nav "Secured by Clerk" trong `sidebar-data.ts`. Không cần login — đúng quyết định "chạy cá nhân trước". Lưu ý: `__root.tsx`/`_authenticated/route.tsx` của template vốn **không hề ép đăng nhập** (không có redirect-if-not-logged-in), nên việc gỡ Clerk chỉ là dọn code chết, không ảnh hưởng luồng vào dashboard. Đã verify `pnpm build` + `pnpm dev` chạy sạch sau khi gỡ.
- Template còn có sẵn các trang demo không cần (`features/chats`, `features/tasks`, `features/apps`, `features/users`) — dọn ở đầu Phase 1 khi bắt đầu thay bằng trang `crawl`/`trend`/`jobs`.
- Chưa dùng Alembic cho migration — MVP dùng `Base.metadata.create_all()` lúc startup vì schema còn đơn giản. Cân nhắc thêm Alembic khi bắt đầu sửa schema có dữ liệu thật cần giữ lại (khoảng Phase 3-4 trở đi).
- `backend/app/adapters/` chưa tạo — sẽ tạo cùng lúc với `BilibiliDownloader` đầu Phase 1 để tránh thư mục rỗng.
- Khi test dev server nhiều lần bằng background task, tiến trình `vite` con đôi khi không bị dọn hết khi dừng task (giữ port bị chiếm) — nếu gặp "Port ... is in use" liên tục, kiểm tra `Get-NetTCPConnection -State Listen` để tìm đúng PID đang giữ cổng rồi tắt, thay vì đoán/tắt hàng loạt tiến trình node.
