# Phase 18: Đăng nhập, Admin, License theo gói & Host đa người dùng

Trạng thái: Chưa bắt đầu — đang ở bước chuẩn bị nguyên liệu (quyết định kỹ thuật + tài khoản bên ngoài), chưa code.

## Quyết định hướng (chốt phiên 2026-09-20 — ĐẢO LẠI quyết định 2026-09-07)

Phase 12 (2026-09-07) đã chốt ưu tiên đóng gói desktop app, tạm gác host multi-tenant SaaS — lý do: chi phí compute Whisper/Demucs khi host cho nhiều người + rủi ro pháp lý khi giúp người lạ scrape/re-up nội dung có bản quyền qua dịch vụ host công khai (xem `docs/phases/phase-12-desktop-packaging.md` mục "Quyết định hướng phân phối" và `docs/phases/phase-7-productization.md`).

**Phiên 2026-09-20: chủ động đảo lại quyết định đó** — đi hướng host web multi-tenant thật, tự chạy pipeline (crawl/dịch/lồng tiếng) cho mọi user trên server của mình, bán license theo gói.

**Cập nhật cùng phiên: mô hình lai, không phải "desktop bỏ hẳn"** — bản host web sẽ bị giới hạn bởi phần cứng server dùng chung (đặc biệt Whisper/Demucs/diarization tốn compute), nên **cho phép user gói trả phí (Pro + ProMax) tải bản desktop** (Phase 12) để tự chạy bằng phần cứng riêng, không bị giới hạn theo tải server. Vì vậy desktop app KHÔNG còn "giữ nguyên, không đụng vào" như dự kiến ban đầu — cần gắn thêm cơ chế xác thực license vào desktop app (xem mục Phạm vi/Kiến trúc dưới), biến nó thành 1 phần phân phối chính thức của Phase 18 chứ không phải nhánh phụ độc lập.

**Rủi ro pháp lý ở Phase 7/12 CHƯA được giải quyết bằng tư vấn pháp lý riêng** — quyết định đảo hướng lần này chấp nhận rủi ro đó để tiến tới, không phải vì rủi ro đã biến mất. Nhắc lại ở đây để phiên sau không hiểu nhầm là đã có tư vấn pháp lý.

## Mục tiêu
Biến app từ "công cụ cá nhân 1 user cố định" thành sản phẩm nhiều user độc lập, đăng nhập được, có trang quản trị cho admin, giới hạn tính năng theo gói (Free/Pro/ProMax), bán license qua cổng thanh toán VN, và host được trên server thật cho nhiều người dùng cùng lúc.

## Phạm vi

**Trong phạm vi:**
- Đăng nhập/đăng ký user thật (email + password), phân quyền `user` vs `admin`.
- Multi-tenant thật: mọi query hiện đang lọc theo `user_id` cố định (xem Phase 7/8 ghi chú) chuyển sang lọc theo user đang đăng nhập — cách ly dữ liệu giữa các user.
- Model License/Subscription: gói (Free/Pro/ProMax), thời hạn, trạng thái (active/expired/cancelled), gắn với user.
- Feature gating theo gói: middleware/dependency kiểm tra quyền trước khi cho chạy 1 tác vụ (vd giới hạn số phút video/tháng, giới hạn provider AI được dùng, bật/tắt tính năng lồng tiếng nhiều giọng của Phase 19, watermark cho gói Free...).
- Trang quản trị admin: danh sách user, xem/sửa gói + hạn dùng, duyệt thanh toán thủ công (nếu chọn hướng thủ công), xem thống kê usage cơ bản.
- Tích hợp thanh toán: cổng VN (PayOS/VNPay/Momo — chốt cụ thể ở mục Nguyên liệu) để user tự mua/gia hạn gói.
- Chuẩn bị hạ tầng host: chọn nhà cung cấp server, deploy backend+frontend+DB, domain, HTTPS, biến `MASTER_KEY`/secrets thành quản lý qua env server thay vì file local.
- Hàng đợi job thật: vì nhiều user chạy job đồng thời trên 1 server, cần đánh giá lại `ProcessPoolExecutor` hiện tại có đủ không hay phải chuyển sang Celery/Redis (đã ghi trong kiến trúc gốc là "khi cần" — thời điểm này là lúc cần).
- **Gắn license vào desktop app** (chốt 2026-09-20): endpoint xác thực license dùng chung cho cả web lẫn desktop; desktop app (Tauri) cần thêm màn hình đăng nhập (hiện chưa có — Phase 12 vốn thiết kế single-user không đăng nhập) + gọi API check license mỗi lần mở app; trang web có khu vực "Tải xuống" hiện link installer cho user thuộc gói Pro/ProMax.

**Ngoài phạm vi (không làm ở phase này):**
- Auto-scaling/multi-server (1 server đơn là đủ cho giai đoạn đầu).
- Subscription tự động gia hạn định kỳ qua cổng thanh toán (bắt đầu bằng license theo kỳ hạn cố định, user tự gia hạn tay khi hết hạn — subscription tự động phức tạp hơn, để sau khi có traffic thật).
- Tư vấn pháp lý chính thức (xem cảnh báo ở trên) — không thuộc phạm vi code.
- Build lại/nâng cấp installer desktop (macOS/Linux, auto-update, code signing) — vẫn theo đúng phạm vi gốc của Phase 12, phase này chỉ thêm lớp xác thực license, không đụng cơ chế đóng gói.
- Cơ chế chống bẻ khoá/anti-piracy nâng cao cho desktop (vd obfuscate, chống bypass check license) — MVP chỉ cần check online đơn giản, chấp nhận rủi ro crack thấp ở giai đoạn đầu ít user.
- Lồng tiếng nhiều giọng (Phase 19) — chỉ cần phase này xong phần feature-gating là đủ để Phase 19 gắn cờ theo gói; phần kỹ thuật diarization/TTS làm ở phase riêng.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [ ] **Chọn nhà cung cấp server/host**: VPS (DigitalOcean/Vultr/Linode) hay cloud có GPU (cần cho Whisper/Demucs nhanh hơn, xem thêm ở Phase 19 nếu làm multi-speaker) — quyết định ảnh hưởng chi phí vận hành hàng tháng, cần bạn chốt ngân sách trước.
- [ ] **Domain** đã có hay cần mua.
- [ ] **Tài khoản merchant cổng thanh toán** (đã chọn PayOS/VNPay/Momo ở phiên trước — cần bạn đăng ký tài khoản merchant thật + lấy API key/secret trước khi code phần tích hợp thanh toán).
- [ ] **Chốt số lượng & giới hạn cụ thể từng gói** (Free/Pro/ProMax): số phút video/tháng, số job đồng thời, provider AI nào được dùng ở gói nào, có watermark hay không, giá tiền từng gói/kỳ hạn (tháng/quý/năm) — đây là quyết định kinh doanh, cần bạn chốt trước khi viết feature-gating logic (không tự đoán).
- [ ] **Quyết định cơ chế session**: JWT (stateless, phù hợp nếu sau này tách API cho mobile/n8n) hay session cookie (đơn giản hơn cho web-only) — đề xuất JWT access+refresh token vì đã có `mcp_access_token.py` dùng pattern token sẵn, nhất quán.
- [ ] **Quyết định cấp license thủ công hay tự động qua webhook thanh toán ngay từ đầu** — đề xuất: bắt đầu thủ công (admin duyệt tay sau khi nhận thanh toán) để ra mắt nhanh, tự động hoá webhook sau khi có traffic thật (đỡ rủi ro bug webhook làm sai lệch license lúc mới launch).
- [ ] **Xác nhận lại phạm vi rủi ro pháp lý** ở mục Quyết định hướng phía trên — bạn đã đọc và chấp nhận, hay muốn giới hạn tính năng crawl/re-up chỉ cho gói cao nhất + có cảnh báo ToS rõ ràng để giảm rủi ro.
- [x] **Gói nào được tải bản desktop**: chốt 2026-09-20 — mọi gói trả phí (Pro + ProMax), Free chỉ dùng bản web.
- [x] **Cơ chế xác thực license cho desktop**: chốt 2026-09-20 — check online mỗi lần mở app (không cache offline dài hạn), nhất quán với việc app vốn đã cần internet để gọi AI provider.

## Kiến trúc đề xuất (cao cấp — chi tiết hoá khi vào code)
- `app/models/user.py`: thêm `password_hash`, `role` (`user`/`admin`), `email` bắt buộc + unique (hiện đang optional).
- `app/models/license.py` (mới): `user_id`, `tier` (free/pro/promax), `status`, `starts_at`, `expires_at`, `payment_ref`.
- `app/core/security.py`: thêm hash password (passlib/bcrypt) + tạo/verify JWT, tách biệt với `encrypt_secret` hiện có (mục đích khác nhau — encrypt_secret là 2 chiều cho API key, password hash là 1 chiều).
- `app/api/deps.py` (mới hoặc mở rộng): dependency `get_current_user`, `require_tier(min_tier)` dùng làm FastAPI dependency chặn ở route level — nhất quán với pattern "route mỏng, business logic ở service" trong `docs/conventions.md`.
- Toàn bộ service hiện có (`video_service`, `crawl_service`...) đổi từ user_id cố định (constant) sang nhận `user_id` thật từ request context — rà soát toàn bộ 26 file đang tham chiếu `user_id` (đã liệt kê ở lần grep chuẩn bị phase này).
- `app/services/license_service.py` (mới): check quyền theo tier, cộng/trừ usage quota.
- `app/services/payment_service.py` (mới) + `app/adapters/payos_adapter.py` (hoặc vnpay/momo tương ứng): tạo link thanh toán, verify webhook signature.
- Frontend: trang `/login`, `/register`, `/admin/users`, `/admin/licenses`, `/pricing` (chọn gói + thanh toán), `/download` (link installer cho gói Pro/ProMax), badge hiện gói hiện tại + usage còn lại trong sidebar.
- Queue: nếu chuyển Celery/Redis — cần thêm `docker-compose` cho Redis, worker process riêng, đổi cách `job.py` hiện tại enqueue (ghi ở kiến trúc gốc `docs/overview/plan.md`).
- `app/api/license.py` (mới): endpoint `POST /api/license/validate` dùng chung cho cả web frontend lẫn desktop app — trả `{tier, status, expires_at}` theo JWT gửi lên.
- `src-tauri/` (Phase 12): thêm màn hình đăng nhập trước khi vào app chính (hiện tại app mở thẳng vào dashboard, không có khái niệm đăng nhập) — lưu JWT bằng cơ chế lưu trữ an toàn của Tauri (không phải localStorage của web), gọi `/api/license/validate` lúc khởi động, chặn vào app nếu tier không đủ/license hết hạn.

## Việc cần làm (chia giai đoạn — mỗi giai đoạn ước lượng ~1 phiên)

### Giai đoạn A — Auth & multi-tenant thật
- [ ] Model `User` thêm password/role, migration.
- [ ] Endpoint đăng ký/đăng nhập/đăng xuất, hash password, tạo JWT.
- [ ] Middleware/dependency lấy user hiện tại từ token, áp vào toàn bộ route hiện có.
- [ ] Rà soát + sửa toàn bộ nơi đang dùng `user_id` cố định → dùng user thật (grep đã có sẵn danh sách 26 file ở trên, dùng lại không cần search lại).
- [ ] Frontend: trang login/register, lưu token, redirect khi chưa đăng nhập, interceptor gắn token vào mọi request API.

### Giai đoạn B — License/tier & feature gating
- [ ] Model `License`, service `license_service`.
- [ ] Dependency `require_tier` áp vào các route cần giới hạn (crawl, dịch, lồng tiếng, video kể chuyện...).
- [ ] UI hiện rõ gói hiện tại + giới hạn còn lại, chặn hành động vượt quota với thông báo rõ ràng (không chỉ trả lỗi 403 trơ).

### Giai đoạn C — Thanh toán & Admin panel
- [ ] Tích hợp cổng thanh toán đã chọn (tạo link thanh toán, trang callback, webhook verify).
- [ ] Cấp license tự động hoặc thủ công theo quyết định ở Nguyên liệu.
- [ ] Trang admin: danh sách user + gói + hạn dùng, sửa tay license (dùng cho case thủ công/hỗ trợ khách), xem log thanh toán.

### Giai đoạn D — Host thật
- [ ] Dockerize backend+frontend (nếu chưa có), deploy lên server đã chọn.
- [ ] Domain + HTTPS (Let's Encrypt hoặc tương đương).
- [ ] Secrets (MASTER_KEY, payment API key...) qua env server, không commit, không dùng file `.env` local như dev.
- [x] **Đã xong 2026-09-20 (sớm hơn dự định)**: `docs/performance-optimization/plan.md` P0 (hết chặn event loop, `asyncio.to_thread`) + P1 (httpx client tái dùng, dọn file tạm, sửa N+1) + P2 (worker pool thật — `app/core/worker_pool.py`, `ProcessPoolExecutor` stdlib cho `transcribe`/`diarize`, KHÔNG dùng Celery/Redis vì Phase 18 chỉ nhắm 1 server đơn, xem lý do đầy đủ trong plan đó) đều đã code + test pass (430 test). Việc còn lại khi vào Phase 18 thật: tăng `cpu_worker_count` (setting mới, mặc định 1) qua env theo số core server thật có, và cân nhắc nâng `batch_service.DEFAULT_CONCURRENCY` (hiện vẫn =1, chưa đổi) khi có tín hiệu thật cần chạy nhiều video đồng thời.
- [ ] Backup DB định kỳ (SQLite hiện tại — cân nhắc có cần chuyển Postgres khi nhiều user ghi đồng thời, SQLite WAL có giới hạn concurrent writer).

### Giai đoạn E — Gắn license vào desktop app
- [ ] Endpoint `POST /api/license/validate` (dùng chung với web).
- [ ] Tauri: màn hình đăng nhập trước khi vào app chính, lưu token an toàn (không phải localStorage web).
- [ ] Tauri: gọi validate lúc khởi động, chặn/nhắc nâng cấp nếu tier không đủ hoặc license hết hạn; xử lý rõ trường hợp mất mạng khi mở app (không cache offline — báo lỗi rõ ràng "cần internet để mở", không phải crash im lặng).
- [ ] Trang web `/download`: hiện link tải installer, chỉ hiện cho user gói Pro/ProMax (ẩn hoặc dẫn tới `/pricing` nếu gói Free).
- [ ] Build lại installer với thay đổi trên, verify chạy thật (đăng nhập → check license → vào app) trên máy Windows sạch tương tự Definition of Done còn thiếu của Phase 12.

## Tiêu chí hoàn thành (Definition of Done)
- [ ] 2 user độc lập đăng ký, đăng nhập, dữ liệu (video/job/api-key) của user này không hiện ra ở user kia — verify thật bằng 2 tài khoản test.
- [ ] Gói Free bị chặn đúng khi vượt giới hạn (vd hết quota phút video/tháng) — verify thật, không chỉ unit test.
- [ ] Mua gói qua cổng thanh toán thật (dù ở môi trường sandbox/test của cổng) → license kích hoạt đúng.
- [ ] Admin đăng nhập thấy được danh sách user + gói, sửa được license tay.
- [ ] App chạy được trên server thật qua domain thật (không phải localhost), HTTPS hoạt động.
- [ ] User gói Pro/ProMax tải + cài desktop app, đăng nhập, license được xác thực đúng; user gói Free không thấy link tải (hoặc bị chặn nếu cố mở app desktop cũ).

## Ghi chú phát sinh trong lúc làm
(Để trống, điền khi bắt đầu code.)
