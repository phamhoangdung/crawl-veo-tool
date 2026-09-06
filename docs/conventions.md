# Coding Conventions

Áp dụng cho toàn bộ các phase trong `docs/phases/`. Đọc file này 1 lần đầu dự án; không cần đọc lại mỗi phiên trừ khi quên quy tắc cụ thể.

## Nguyên tắc chung
- Rõ ràng hơn khéo léo — ưu tiên code dễ đọc hơn cách viết ngắn/thông minh khó hiểu.
- Không thêm abstraction/tính năng ngoài phạm vi phase đang làm (xem "Phạm vi" trong từng file phase). 3 dòng lặp lại còn hơn 1 abstraction sớm.
- Comment tối thiểu — chỉ viết khi giải thích lý do không hiển nhiên (constraint ẩn, workaround, quyết định gây bất ngờ), không viết comment mô tả code làm gì.

## Backend (Python/FastAPI)
- Python 3.11+, **type hint bắt buộc** trên mọi function signature (tham số + return).
- Format/lint bằng `ruff` (gộp cả format + lint) — chạy `ruff check .` và `ruff format .` trước khi coi 1 việc là xong.
- Pydantic models cho **mọi** request/response schema đi qua API — không trả dict thô qua boundary API.
- Kiến trúc phân lớp, một chiều:
  - `app/api/` — route handler, **mỏng**: chỉ validate input (Pydantic) + gọi service, không chứa business logic.
  - `app/services/` — business logic (vd orchestrate pipeline job).
  - `app/adapters/` — gọi ra ngoài: downloader (Bilibili/Douyin), provider AI (translate/transcribe/tts), ffmpeg. Route handler **không được** gọi thẳng adapter, phải qua service.
  - `app/models/` — SQLAlchemy ORM.
- Custom exception class cho lỗi nghiệp vụ (vd `VideoNotFoundError`, `ProviderQuotaExceededError`), bắt bằng FastAPI exception handler tập trung — không dùng bare `except:`.
- Logging bằng module `logging` chuẩn, kèm `job_id`/`video_id` trong context khi xử lý job — không dùng `print()`.
- Test bằng `pytest`; mỗi adapter provider có ít nhất 1 test (mock HTTP call), đặt trong `tests/` mirror cấu trúc `app/`.
- **Không bao giờ log giá trị API key**, kể cả lúc debug — chỉ log việc dùng provider nào, không log key.

## Frontend (React/TypeScript)
- Áp dụng skill **`vercel-react-best-practices`** (đã cài global, xem dưới) cho mọi code React/TS trong `frontend/` — quy tắc component structure, hooks, performance theo chuẩn Vercel.
- Giữ nguyên eslint/prettier config có sẵn từ template [satnaing/shadcn-admin](https://github.com/satnaing/shadcn-admin), không tự ý đổi rule.
- Component nhỏ, tách theo trang khớp module trong plan (`pages/crawl`, `pages/trend`, `pages/jobs`, `pages/library`, `pages/settings`), tái dùng UI primitives sẵn có của shadcn (Button, Card, Table, Dialog...) thay vì tự viết lại.
- Gọi API qua 1 lớp client tập trung (vd `lib/api.ts`), không fetch rải rác trong từng component.

## Git & quy trình
- Commit message ngắn gọn, tập trung "why" hơn "what".
- Mỗi phase (`docs/phases/phase-N-*.md`) nên gói gọn trong 1 hoặc vài commit rõ ràng — không gộp nhiều phase vào 1 commit lớn.
- Sau khi hoàn thành 1 phase, chạy skill **`code-review`** có sẵn trong Claude Code (không cần cài thêm, gõ `/code-review`) để bắt lỗi correctness + cơ hội đơn giản hoá, trước khi đánh dấu phase "Hoàn thành" trong CLAUDE.md.

## Skill đã cài để hỗ trợ code chất lượng cao
| Skill | Phạm vi | Nguồn | Installs |
|---|---|---|---|
| `vercel-react-best-practices` | React/TypeScript | Chính chủ Vercel (`vercel-labs/agent-skills`) | 692K+ |
| `code-review` (built-in Claude Code, không qua npx skills) | Review code trước khi merge, mọi ngôn ngữ | Anthropic | — |

**Chưa có skill tương đương cho Python/FastAPI**: đã tìm trên skills.sh nhưng không có skill nào đạt ngưỡng tin cậy (1K+ installs, nguồn rõ ràng) dành riêng cho Python/FastAPI best practices — cao nhất chỉ ~600 installs từ tác giả không rõ uy tín. Vì vậy phần quy tắc Backend ở trên được viết thủ công dựa trên chuẩn cộng đồng Python phổ biến, không tự động hoá qua skill. Nếu sau này skills.sh có lựa chọn tốt hơn, cập nhật lại mục này.
