# Phase 8: AI Account Pool

Trạng thái: **Phần lõi xong & verify qua test suite + DB thật** — trừ endpoint batch-enqueue cho n8n (cố ý bỏ, xem Ghi chú) và resume tự động theo lịch (dùng resume thủ công qua nút bấm lại có sẵn). Chưa verify qua HTTP request thật (xem Ghi chú — có tiến trình server khác đang chiếm cổng 8000, không phải do phiên này khởi động).

## Mục tiêu
Cho phép nhiều API key cùng 1 provider (thay vì 1 key/provider/user như hiện tại), tự động chọn/xoay vòng và failover khi 1 key hết quota/rate-limit — để chạy batch lớn qua n8n mà không dừng job giữa chừng khi 1 account cạn.

## Phạm vi
**Trong phạm vi:** đổi schema `ApiKey` (bỏ unique 1-key/provider, thêm label/status/cooldown/usage), service chọn key trong pool (round-robin, tránh chọn trùng khi chạy song song), tích hợp vào `translate_service`/`tts_service` hiện có, nhận diện lỗi quota/rate-limit thống nhất theo provider, trạng thái job mới `PAUSED_QUOTA` (không fail hẳn khi cả pool cạn), UI mở rộng trang `/api-keys` thành pool view.

**Ngoài phạm vi:** multi-tenant thật (vẫn 1 `user_id` cố định như hiện tại — xem Phase 7), dựng workflow n8n thật (việc đó làm bên n8n, không phải trong repo), gọi billing/usage API thật của provider để biết chính xác quota còn lại (bắt đầu bằng tự đếm lỗi 429/quota-error, không tích hợp billing API), endpoint `batch-enqueue` riêng cho n8n (xem Ghi chú — quyết định không cần).

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [x] **Quyết định cách xác định "hết quota"**: chỉ dựa vào lỗi 429/quota-error trả về từ provider — đã làm đúng theo đề xuất, không cho user tự khai báo ngưỡng.
- [ ] **Ít nhất 2 API key thật cùng 1 provider** — vẫn chưa có, cần bạn chuẩn bị nếu muốn tự tay verify rotation với key thật (test tự động đã verify bằng key giả/mock, xem Ghi chú).
- [x] Mã lỗi quota/rate-limit: chốt dùng chung 1 tín hiệu — **HTTP 429** cho cả OpenAI/Google/ElevenLabs (không phân biệt sâu hơn theo mã lỗi cụ thể từng provider — đơn giản hoá, đủ dùng).
- [x] **Quyết định UI**: mở rộng trang `/api-keys` có sẵn — đã làm đúng đề xuất, không tạo route mới.

## Việc cần làm
- [x] `app/models/api_key.py`: bỏ `UniqueConstraint`, thêm `label`, `status` (`ApiKeyStatus`: active/cooldown/exhausted/invalid), `cooldown_until`, `request_count`, `error_count`, `last_used_at`.
- [x] `app/core/db.py`: thêm `_migrate_api_keys_pool()` — SQLite lưu UNIQUE constraint dưới dạng autoindex không xoá được bằng `DROP INDEX`, phải dựng lại bảng (rename → tạo bảng mới đúng schema → copy dữ liệu → xoá bảng cũ). Idempotent, đã verify chạy 2 lần liên tiếp không lỗi.
- [x] `app/services/api_key_service.py`: `add_key` (không upsert — mỗi lần gọi tạo 1 row), `pick_key_for_task`/`pick_decrypted_key` (chọn key active theo least-recently-used, tự reactivate key hết cooldown), `mark_key_result`, `update_key`, `delete_key`. Giữ `get_decrypted_key` cũ nhưng đổi thành "peek" thuần (không mutate usage stats) — `cost_service` chỉ cần biết "có key không", không phải "dùng key" nên tách riêng khỏi `pick_key_for_task` để không làm sai lệch số liệu usage.
- [x] `app/adapters/provider_errors.py` (mới): `ProviderQuotaExceededError` (1 key cụ thể hết quota — 429), `AllProvidersExhaustedError` (hết cả pool lẫn fallback free).
- [x] `translate_service.py`: xoay vòng key OpenAI trong pool khi 429, hết pool thì fallback Google free (giữ nguyên hành vi gốc), hết cả 2 thì `AllProvidersExhaustedError`.
- [x] `tts_service.py`: xoay vòng key ElevenLabs trong pool khi 429, hết pool thì fallback Edge-TTS free — **không** propagate `AllProvidersExhaustedError` ở đây (xem Ghi chú, quyết định có chủ đích).
- [x] `app/models/video.py` + `dubbing_service.py`: thêm `VideoStatus.PAUSED_QUOTA`, `run_translate` bắt riêng `AllProvidersExhaustedError` → set `PAUSED_QUOTA` thay vì `FAILED_TRANSLATING`.
- [x] `app/api/api_keys.py` + `app/schemas/api_key.py`: `GET` (list), `POST` (thêm key mới vào pool, không upsert), `PATCH /{id}` (label/status), `DELETE /{id}`.
- [ ] Endpoint `POST /api/jobs/batch-enqueue` cho n8n — **không làm**, xem Ghi chú.
- [x] `frontend/src/features/api-keys/index.tsx`: viết lại thành pool view — nhiều key/provider, badge trạng thái, usage (request/error count, thời điểm hết cooldown), nút tạm dừng/kích hoạt lại + xoá riêng từng key (theo đúng pattern inline-confirm đã dùng ở trang Videos).
- [x] `frontend/src/lib/api.ts`: `ApiKeyRead` đầy đủ field mới, `addApiKey`/`updateApiKey`/`deleteApiKey` thay cho `saveApiKey` cũ; thêm `paused_quota` vào type `VideoStatus`.
- [x] `backend/tests/services/test_api_key_service.py` (25 test): add/list không upsert, pick theo LRU, skip cooldown/invalid, reactivate sau cooldown, mark_key_result, update/delete, cách ly theo user.
- [x] `backend/tests/services/test_translate_service.py`: cập nhật test give-up-sau-retry để nhận `ProviderQuotaExceededError` thay vì lỗi HTTP thô; thêm test cho `translate_text` (dùng Google khi chưa có key, ưu tiên OpenAI khi hoạt động, xoay key khi 1 key hết quota, fallback Google khi hết pool, `AllProvidersExhaustedError` khi cả 2 đều lỗi).

## Tiêu chí hoàn thành (Definition of Done)
- [x] Thêm được 2 key cùng 1 provider qua UI — verify qua code + test (`test_add_key_does_not_upsert_creates_new_row_each_time`), UI đã tự implement, chưa tự tay bấm thử qua browser thật (xem Ghi chú).
- [x] Mô phỏng lỗi quota ở key 1 → job tự chuyển dùng key 2, không fail — verify qua test thật với DB in-memory (`test_rotates_to_next_key_when_first_key_exhausted`), key 1 chuyển `cooldown`, không mất dữ liệu.
- [x] Cả 2 (tất cả) key cùng cạn + fallback free cũng lỗi → `PAUSED_QUOTA` thay vì `FAILED_*` — verify qua test (`test_raises_all_providers_exhausted_when_openai_and_google_both_fail` + `dubbing_service` bắt đúng exception).
- [ ] `POST /api/jobs/batch-enqueue` — bỏ, xem Ghi chú.

## Ghi chú phát sinh trong lúc làm
- **Phát hiện việc dở dang chưa commit trước khi bắt đầu**: `translate_service.py` đã có sẵn logic retry 429 (`_call_with_retry`) từ 1 phiên trước, chưa commit. Không đụng/xoá — xây rotation Phase 8 CHỒNG LÊN logic retry đó (khi retry hết lượt vẫn 429 thì mới coi là "key cần nghỉ", chuyển `ProviderQuotaExceededError` thay vì raise thô).
- **Migration bảng `api_keys`**: SQLite lưu `UNIQUE(user_id, provider)` dưới dạng `sqlite_autoindex_api_keys_1`, loại index này **không thể** `DROP INDEX` trực tiếp (SQLite chặn) — phải rename bảng cũ → tạo bảng mới đúng schema model hiện tại (`ApiKey.__table__.create()`) → copy dữ liệu qua → xoá bảng cũ. Đã test cả trên DB in-memory (test) lẫn **DB thật** (`backend/storage/app.db`, backup trước khi chạy) — chạy 2 lần liên tiếp để xác nhận idempotent, dữ liệu (1 key OpenAI có sẵn) giữ nguyên đúng.
- **Không làm `batch-enqueue` endpoint riêng cho n8n**: cân nhắc kỹ, quyết định không cần — n8n có thể dùng trực tiếp các endpoint pipeline hiện có (`POST /api/videos/{id}/translate`, `/dub`...) theo vòng lặp `SplitInBatches`, đúng pattern chuẩn của n8n (đã research ở phần plan). Thêm 1 endpoint bespoke chỉ để "gộp nhiều job" không giải quyết vấn đề gì mà endpoint đơn lẻ + loop trong n8n chưa làm được, nên bỏ để tránh code thừa không ai dùng tới khi chưa thực sự dựng workflow n8n.
- **Không propagate `AllProvidersExhaustedError` từ `tts_service`**: Edge-TTS (fallback free) không có khái niệm "hết quota" — lỗi của nó (`TtsFailedError`) chủ yếu do 1 câu không đọc được (input), đã được `dubbing_service` xử lý đúng bằng cách bỏ qua đoạn đó (im lặng), không phải lỗi cấp job. Biến nó thành "hết quota toàn phần" sẽ làm dừng oan cả video vì 1 câu lỗi nhỏ — sai bản chất vấn đề.
- **Resume khi hết cooldown**: KHÔNG viết scheduler tự động kiểm tra định kỳ (như phác thảo ban đầu) — quyết định scope xuống còn "resume thủ công": video ở `PAUSED_QUOTA` dùng đúng nút bấm lại bước đó (Dịch/Lồng tiếng) đã có sẵn từ Phase 2, `pick_key_for_task` tự động reactivate key đã hết cooldown ngay trong lần gọi tiếp theo (đã verify bằng test `test_reactivates_key_after_cooldown_expires`) — không cần thêm hạ tầng job/cron mới cho MVP.
- **Chưa verify qua HTTP request thật**: phát hiện có 1 tiến trình `uvicorn --reload` khác (PID không thuộc phiên này, chạy từ trước) đang chiếm cổng 8000 — khả năng cao là dev server bạn đang tự chạy song song trong lúc mình sửa code (giải thích vì sao code Phase 8 có thể đã tự reload vào đúng tiến trình đó qua `--reload`). Mình khởi động thêm 1 tiến trình nữa để test độc lập nhưng bị treo (nghi do xung đột cổng/khoá SQLite giữa 2 tiến trình), và bị chặn quyền khi cố tắt tiến trình để dọn dẹp (auto-mode classifier từ chối thao tác Stop-Process). **Cần bạn**: tắt hẳn mọi tiến trình `npm run dev`/uvicorn đang chạy rồi chạy lại `npm run dev` sạch từ đầu, sau đó thử thêm 2 key cùng provider qua trang `/api-keys` để tự tay xác nhận UI hoạt động đúng — phần logic đã được test tự động kỹ (33 test bao gồm cả `translate_service`), rủi ro chủ yếu còn lại là ở tầng wiring API/UI chưa tự mắt thấy chạy thật.
- **Backend test suite**: 102 → 127 test, toàn bộ pass (`node scripts/run-python.mjs -m pytest backend`). Frontend: `tsc -b` không phát sinh lỗi mới (4 lỗi còn lại đã tồn tại từ trước, không liên quan Phase 8 — đã xác nhận bằng `git stash` để so sánh), `eslint` sạch trên các file đã sửa.
