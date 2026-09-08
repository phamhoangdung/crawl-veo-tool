# Phase 6: Hardening & Ops

Trạng thái: **Phần cốt lõi xong & verify thật** (storage cleanup, health-check, setup docs). Celery/Redis: quyết định KHÔNG cần — xem Ghi chú.

## Mục tiêu
Ổn định hoá tool cho vận hành lâu dài ở quy mô cá nhân (chưa phải multi-tenant/bán — đó là [phase-7-productization.md](phase-7-productization.md), tương lai).

## Phạm vi
**Trong phạm vi:** đánh giá nâng cấp Celery/Redis nếu `ProcessPoolExecutor` không đủ, storage cleanup/retention, unit test cho adapter, health-check định kỳ cho downloader, packaging môi trường Windows.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [x] Số liệu thực tế về concurrency: **chưa từng có job đồng thời thật nào** qua Phase 1-5 — mọi request xử lý tuần tự trong 1 request HTTP, `ProcessPoolExecutor` (đã dự tính từ Phase 0) chưa từng được implement vì chưa cần. Kết luận: chưa cần Celery/Redis (xem Ghi chú).
- [x] Đã đọc lại "Ghi chú phát sinh" các phase 0-5 để biết ưu tiên hardening: lỗi hay gặp nhất là (1) tiến trình `uvicorn --reload` không thay hẳn worker khi code đổi, (2) DB schema không tự migrate khi thêm cột mới, (3) PATH ffmpeg không refresh trong terminal đang mở.

## Việc cần làm
- [x] `app/services/storage_cleanup_service.py`: `cleanup_old_job_folders(max_age_days)` xoá thư mục job cũ (theo mtime), `get_storage_usage_bytes()` — chưa nối lên API/cron, xem Ghi chú.
- [x] Test cho adapter/service đã có coverage đầy đủ: `bilibili/client.py` (5 test), `cost_service` (2), `dubbing_service` time-stretch logic (3), `subtitle_service` (3), `storage_cleanup_service` (2) — tổng 15 test, tất cả mock/không gọi mạng thật.
- [x] `app/services/health_check_service.py` + `GET /health/downloader` — gọi thật 3 endpoint Bilibili (popular/ranking/search), verify bằng request thật. **Bắt được 1 lỗi thật ngay khi viết**: dùng nhầm `day=1` (giá trị không hợp lệ cho endpoint ranking) — sửa thành `day=3`, xác nhận lại `healthy: true`. Douyin không có health-check vì adapter chưa verify được (Phase 3).
- [x] `SETUP.md` — hướng dẫn cài đặt Windows đầy đủ, viết dựa trên các vướng mắc **thật đã gặp** trong suốt quá trình build (không phải đoán trước): lỗi PATH ffmpeg, lỗi WinError 10013, lỗi thiếu cột DB.
- [ ] Nối `cleanup_old_job_folders` lên 1 endpoint/cron thật — code đã có, chưa có nơi gọi định kỳ (không có scheduler trong dự án, cần quyết định dùng gì — cron ngoài gọi 1 endpoint, hay APScheduler trong app — để phiên sau).

## Tiêu chí hoàn thành (Definition of Done)
- [~] Tool chạy ổn định qua nhiều batch lớn liên tục — chưa test thật với batch lớn (nhiều job/video cùng lúc), vì chưa có nhu cầu thật để tạo tình huống đó. Storage cleanup đã sẵn sàng nhưng chưa được gọi tự động.
- [x] Có test tự động chạy pass cho các adapter chính — 15/15 test pass, verify thật (không chỉ báo cáo).
- [x] Có tài liệu cài đặt đủ để tự cài lại từ đầu — `SETUP.md`, dựa trên kinh nghiệm thật.

## Ghi chú phát sinh trong lúc làm
- **Quyết định không làm Celery/Redis**: toàn bộ dự án tới giờ chạy đồng bộ trong request HTTP (không có `ProcessPoolExecutor` thật, dù Phase 0 dự tính dùng nó). Việc này hoạt động ổn cho quy mô cá nhân xử lý 1 video tại 1 thời điểm (đúng use case thật đã test). Thêm Celery/Redis lúc này là over-engineering không có bằng chứng cần thiết — đúng tinh thần "không thêm abstraction chưa cần" trong `docs/conventions.md`. Nên làm khi thực sự có nhu cầu chạy nhiều video song song.
- **Health-check tự bắt lỗi ngay trong lúc viết nó** (dùng sai giá trị `day` cho ranking endpoint) — minh chứng cho giá trị thật của tính năng này: không chỉ để phát hiện Bilibili đổi API, mà còn bắt được lỗi code của chính mình trước khi thành bug âm thầm.
- Storage cleanup viết xong nhưng chưa nối lên chỗ nào gọi định kỳ — dự án chưa có concept "scheduler/cron job" nội bộ, cần quyết định hướng (cron hệ điều hành gọi 1 endpoint, hay thêm APScheduler chạy trong process) trước khi làm tiếp, không tự chọn thay vì để đó không dùng được.

## Tải chạy nền + trang Quản lý file (phiên 2026-09-07)

**Vấn đề gốc**: `POST /api/videos/{id}/download` chạy **đồng bộ trong request** — frontend gửi rồi chờ đến khi tải xong. Hệ quả: nút chỉ hiện "Đang xử lý" không có %, rời trang là mất dấu, đóng tab thì tải dở dang.

**Đã sửa**:
- Endpoint download dùng `BackgroundTasks`: đổi trạng thái sang `downloading`, đăng ký task, **trả về ngay (đo được 0.06s)**. Hàm `_run_download` tự mở `SessionLocal()` riêng vì session của request đã đóng khi nó chạy.
- Gọi download khi video đang tải → **409** thay vì tạo 2 luồng tải song song cùng file.
- `DownloadDock` (`components/download-dock.tsx`) gắn trong `authenticated-layout` nên **hiện ở mọi trang**, thu gọn được, poll 800ms và tự dừng khi mọi mục đã kết thúc.
- Trang Crawl thu hẹp lại: chỉ tìm + tải. Các bước xử lý chuyển sang trang Quản lý file.

**Trang Quản lý file** (`/files`, `features/files/`, API `app/api/files.py` + `file_manager_service.py`):
- Liệt kê từng video kèm các biến thể file (gốc / lồng tiếng / có phụ đề) và **dung lượng thật đọc từ đĩa**, không tin DB.
- Tổng quan dung lượng + phát hiện **file mồ côi** (còn trên đĩa nhưng không video nào trỏ tới) và nút dọn. Lần chạy đầu đã giải phóng 39.8 MB rác từ job test.
- Nút chạy bước tiếp theo của pipeline theo trạng thái (`NEXT_STEP`), gồm cả các nhánh `failed_*` để thử lại — chỉ hiện đúng 1 hành động vì pipeline là tuần tự.
- Xoá từng biến thể hoặc cả thư mục. **Xoá file gốc sẽ reset status về `queued`** — nếu không UI vẫn tưởng file còn đó và bước sau sẽ lỗi khi mở file.
- Mở Finder/Explorer tới đúng file.

**Lưu ý khi đóng gói thành app desktop**: `BackgroundTasks` chạy trong process uvicorn, đủ cho 1 người dùng local. Nếu chuyển sang nhiều worker thì cả `progress_service` (dict in-memory) lẫn background task đều phải chuyển sang Celery/Redis.

**Bẫy đã gặp trong test**: pragma `foreign_keys=ON` đăng ký toàn cục ở `core/db.py` áp dụng cả với engine in-memory của test — phải commit `User` trước khi chèn `Job` tham chiếu nó, không thì `FOREIGN KEY constraint failed`.

### Icon monitor trên topbar + mọi bước pipeline chạy nền (phiên 2026-09-07, phần 2)

**Vấn đề**: chỉ download có tiến độ; tách lời thoại / dịch / lồng tiếng vẫn chạy **đồng bộ trong request** nên UI treo và không biết đang làm gì.

**Đã làm**:
- `progress_service` chuyển từ chuyên-download sang **tracker chung**: `TaskKind` = download | transcribe | translate | dub | burn. Khoá theo `(video_id, kind)` nên 1 video chạy nhiều loại tác vụ không ghi đè nhau (đã verify: transcribe + translate song song trên cùng video). Field đổi tên `downloaded_bytes/total_bytes` → `current/total` vì giờ đếm cả byte lẫn số câu.
- `transcribe` / `translate` / `dub` đều dùng `BackgroundTasks` như download: trả về ngay (đo 0.04s), tự mở `SessionLocal()` riêng, kiểm tra `is_running()` → **409** nếu đang chạy, validate tiền đề → **400** (chưa tải video / chưa có lời thoại).
- Tiến độ theo bước:
  - **Dịch**: đếm theo từng câu → có % thật (verify: 1/32 câu, 3.1%).
  - **Lồng tiếng**: đếm theo câu ở chặng tạo giọng, rồi chặng `separating` (Demucs) → `muxing`.
  - **Tách lời thoại**: faster-whisper chạy liền mạch, **không chia nhỏ được** → chỉ báo chặng, UI hiện thanh `animate-pulse` thay vì đứng im ở 0%.
- `TaskMonitor` (`components/task-monitor.tsx`) — icon Activity trên **topbar của mọi trang**, badge đếm số tác vụ đang chạy (badge đỏ nếu có lỗi), popover liệt kê từng tác vụ kèm icon riêng theo loại, % và nút mở thư mục / bỏ khỏi danh sách / "Dọn xong". Thay cho `DownloadDock` nổi ở góc (đã xoá).
- Poll 800ms khi có tác vụ chạy, **5s khi rỗng** — vẫn bắt được tác vụ khởi động từ trang khác.
- `DELETE /api/downloads/progress/finished` dọn mọi tác vụ đã kết thúc. Khai báo **trước** route `/{video_id}` để không bị bắt nhầm (đã verify).

**Lưu ý**: query key của monitor là `['tasks']` — chỗ nào bấm nút chạy tác vụ thì phải `invalidateQueries({ queryKey: ['tasks'] })` để icon cập nhật ngay.

### Tách list / detail cho trang video (phiên 2026-09-07, phần 3)

Đổi tên **"Quản lý file" → "Video của tôi"** (`/files` → `/videos`, `features/files/` → `features/videos/`) và tách hai tầng:

- **Danh sách** (`features/videos/index.tsx`): chỉ hiển thị — thumb, tiêu đề, trạng thái (nhãn tiếng Việt qua `STATUS_LABELS`, không phơi tên enum), dung lượng, số file, thanh tiến độ của tác vụ đang chạy. Hành động duy nhất là **xoá video** (có bước xác nhận) và mở chi tiết. Bấm thumb / tiêu đề / nút "Chi tiết & xử lý" đều mở.
- **Chi tiết** (`video-detail-sheet.tsx`, Sheet trượt phải): mọi thao tác pipeline nằm ở đây — tải, tách lời, dịch, lồng tiếng, ghép phụ đề. Mỗi bước là 1 hàng có nút Chạy riêng, **thanh % riêng cho đúng tác vụ đó** (lọc từ `['tasks']` theo `video_id` + `kind`), kèm danh sách file (tải/xoá từng biến thể) và toàn bộ lời thoại song ngữ.

Điểm đáng chú ý: mỗi bước có `requires()` kiểm tra tiền đề ở **frontend** (`hasFile` / `hasTranscript` / `hasTranslation`) → nút bị khoá kèm lý do ("Cần tách lời thoại trước") thay vì để người dùng bấm rồi nhận 400 từ backend. Backend vẫn validate độc lập — đây là lớp trải nghiệm, không phải lớp bảo vệ.

`GET /api/videos/{id}` được bổ sung `title`, `author_name`, `cover_url`, `source_url`, `duration_seconds`, `local_path`, `error_message` (đều optional để các endpoint pipeline chỉ trả trạng thái không phải nạp đủ).

### Cá nhân hoá thương hiệu (phiên 2026-09-07, phần 4)

Tên phần mềm: **VieDub Studio**. Chủ sở hữu: DzungPH — phamhoangdung189@gmail.com.

- `frontend/src/config/app.ts` là **nguồn duy nhất** cho `APP_NAME`, `APP_TAGLINE`, `APP_DESCRIPTION`, `APP_OWNER`. Đổi tên sau này chỉ sửa 1 file.
- Đã xoá sạch dấu vết template `satnaing` / `shadcn-admin`: sidebar, profile dropdown, trang auth, `index.html` (title + description; **bỏ hẳn thẻ Open Graph/Twitter** vì app chạy local, không chia sẻ link công khai), `package.json`, id/title trong `logo.tsx`.
- **Bỏ `TeamSwitcher`** (dropdown chọn team với Acme Inc/Acme Corp. giả) → thay bằng `app-brand.tsx` hiển thị tên app + tagline. Tool 1 người dùng local không có khái niệm team. Xoá luôn `app-title.tsx` (chỉ tồn tại trong comment hướng dẫn của template) và type `Team`.
- **Sidebar tổ chức lại theo luồng làm việc** thay vì nhóm demo: "Nội dung" (Tổng quan → Xu hướng → Tìm & tải → Video của tôi → Thư viện) và "Hệ thống" (API Keys, Cài đặt, Trợ giúp). Bỏ hẳn nhóm "Pages" chứa các trang Auth/Errors demo — thứ lộ rõ nhất đây là template.
- **Dashboard viết lại bằng số liệu thật**: bỏ "Total Revenue $45,231", "Subscriptions" và các component `overview/analytics/recent-sales` dùng dữ liệu bịa. Thay bằng `GET /api/files/dashboard-stats` đếm từ DB (video đã tải / tách lời / dịch / lồng tiếng / lỗi / dung lượng / tác vụ đang chạy), kèm danh sách video gần đây và các nút bắt đầu nhanh.

### Thay polling bằng SSE (phiên 2026-09-07, phần 5)

**Vấn đề**: frontend poll `GET /api/downloads/progress` mỗi 800ms–5s từ nhiều component cùng lúc.

**Đã làm** — chọn SSE (không phải WebSocket) vì luồng dữ liệu một chiều server→client, `EventSource` tự lo reconnect, và FastAPI chỉ cần `StreamingResponse`:

- `GET /api/downloads/stream` đẩy tiến độ qua Server-Sent Events. **Chỉ gửi khi payload khác lần trước** (so chuỗi JSON), tick kiểm tra 0.5s. Có heartbeat comment (`: keep-alive`) mỗi 15s để proxy/trình duyệt không coi kết nối là chết. Header `X-Accel-Buffering: no` để nginx không gom event.
- `hooks/use-task-progress.ts`:
  - `useTaskProgressStream()` mở kết nối và ghi vào cache react-query key `['tasks']`. **Chỉ gọi ở MỘT nơi** — `TaskMonitor`, vốn có mặt trên mọi trang. Gọi nhiều nơi = nhiều kết nối.
  - `useTaskProgress()` chỉ đọc cache, dùng ở danh sách video và detail sheet.
  - **Polling dự phòng**: khi `onerror` bắn (backend chưa chạy, proxy chặn stream), trạng thái kết nối ghi `false` vào cache và polling 1.5s tự bật lại. Không bao giờ mất theo dõi tiến độ.

**Đo thật**: 10 giây có tác vụ chạy → **1 request** (`/stream`) + 2 event đúng lúc đổi trạng thái, **0 request** tới `/progress`. Trước đó cùng khoảng thời gian là ~12 request polling.

`GET /api/downloads/progress` vẫn giữ — làm đường dự phòng và tiện gọi tay khi debug.

### Chi tiết video thành trang riêng (phiên 2026-09-07, phần 6)

Đổi từ Sheet trượt phải sang **trang riêng có URL**: `/videos/$videoId` (`features/videos/video-detail.tsx`). Sheet bó hẹp chỗ trong khi đây là nơi làm việc chính.

Lợi ích ngoài không gian: URL chia sẻ/bookmark được, nút back của trình duyệt hoạt động, và F5 không mất chỗ đang xem.

- Bố cục 2 cột: cột trái (1/3) ảnh + danh sách file, cột phải (2/3) các bước xử lý + phụ đề. Có nút back về danh sách.
- Danh sách video chuyển từ `onClick` mở sheet sang `<Link>` — thumb, tiêu đề, nút "Chi tiết & xử lý" đều điều hướng.
- Xoá `video-detail-sheet.tsx`.

**Endpoint mới** `GET /api/files/{video_id}` trả file của 1 video — trang chi tiết không cần nạp cả danh sách. **Khai báo cuối file `api/files.py`**: route có path param sẽ bắt nhầm `/summary` và `/dashboard-stats` nếu đặt trước chúng (đã gặp thật khi thêm, verify lại cả 3 route sau khi sửa thứ tự).

**Lưu ý fast-refresh**: file route chỉ export `Route`; component lấy `videoId` qua `useParams({ from: ... })` thay vì nhận props. Export thêm component trong file route làm lint `react-refresh/only-export-components` cảnh báo.

### Bố cục lại trang chi tiết video (phiên 2026-09-08)

Trang đổ **7 card ngang hàng** lên cùng một màn hình (ảnh cover, File, Các bước xử lý, Phụ đề, rồi Xem trước + Timeline + Cắt clip từ editor) — không có thứ bậc, không thấy đâu là việc đang cần làm.

Chia thành **3 tab** theo 3 việc khác nhau:
- **Xử lý** — các bước pipeline (cột rộng, `lg:col-span-3`) + danh sách File (cột hẹp, `lg:col-span-2`, đặt `order-2` nên nằm bên phải trên màn rộng và xuống dưới trên mobile).
- **Phụ đề** — bảng phụ đề song ngữ. Bỏ giới hạn 5 câu vì giờ có cả trang; nút "Sửa kèm video" mở `SubtitleEditor` như cũ. Tab bị disable khi chưa tách lời thoại.
- **Dựng video** — `TimelineEditor`. Tab bị disable khi chưa tải video. Chỉ mount khi mở tab: editor tải waveform + video, không nên chạy nền khi đang ở tab khác.

Ảnh cover to ở cột trái bị bỏ (không mang thông tin gì, đã thấy ở danh sách video) — thay bằng thumbnail nhỏ cạnh tiêu đề ở header, ẩn trên mobile.

`SubtitleEditor` (Dialog) đặt **ngoài** `Tabs` — nó phủ toàn màn hình nên không thuộc tab nào.

### Tối ưu cho sản xuất hàng loạt (phiên 2026-09-08, phần 2)

**Đo thật trước khi tối ưu** (5 câu rồi ngoại suy cho video 32 câu):

| Bước | Tuần tự | Song song | Nhanh hơn |
|---|---|---|---|
| Dịch | ~8s | ~2s | 3.8x |
| TTS (sinh giọng) | ~54s | ~5s | **10.2x** |

TTS là điểm nghẽn lớn nhất — cả 2 bước đều chờ mạng nên song song có tác dụng rõ.

**Đã sửa** (`dubbing_service.py`): dịch và TTS chạy song song với `asyncio.Semaphore(8)`. Giới hạn 8 để không bị provider chặn rate limit; cao hơn cũng không nhanh thêm vì nghẽn ở mạng. Riêng TTS **tách 2 giai đoạn**: sinh giọng song song (chờ I/O) rồi mới ghép tuần tự (`overlay` là xử lý audio CPU, song song không nhanh hơn). `asyncio.gather` giữ nguyên thứ tự đầu vào nên timeline không bị xáo.

**Batch API** (`app/api/batch.py` + `services/batch_service.py`) — thứ thực sự chặn sản xuất hàng loạt: trước đó 191 video chờ mà mỗi video phải bấm 5 nút, và bước sau chỉ bấm được khi bước trước xong.

- `POST /api/batch/start` — chạy cả pipeline cho danh sách video, **trả về ngay** rồi chạy nền (n8n không phải giữ kết nối mở hàng giờ). Tách `prepare_batch` (dựng job, trả trạng thái ban đầu) khỏi `execute_batch` (chạy thật).
- `GET /api/batch/status` — tiến độ từng video, biết đang ở bước nào.
- `POST /api/batch/cancel` — dừng **sau khi video đang chạy xong**, không cắt ngang để khỏi bỏ file dở dang.
- `GET /api/batch/pending-videos?limit=` — id video chưa xử lý xong, đưa thẳng vào `/start`. Dành cho n8n gọi theo lịch.
- **Bỏ qua bước đã có kết quả** (`_pick_pending_steps`): chạy lại batch không làm lại từ đầu. Verify thật: video 101 đã xong → `done` ngay, không chạy bước nào.
- **1 video lỗi không chặn cả batch** — đánh dấu `failed` kèm bước hỏng rồi chuyển video tiếp theo.
- `DEFAULT_CONCURRENCY = 1`: whisper/demucs đã ăn hết CPU, chạy 2 video song song chỉ làm cả hai cùng chậm và tranh RAM. Cho phép chỉnh lên tối đa 4 nếu máy khoẻ.

`run_step()` trong `pipeline.py` **ném lỗi ra ngoài**, khác các hàm `_run_*` chạy nền nuốt lỗi — batch cần biết bước nào hỏng.
