# Phase 20: Gộp "Xu hướng" + "Tìm & tải" thành một màn Khám phá

Trạng thái: **Code xong, verify chắc chắn qua test suite** (2026-09-22) — 538 test backend + 219 test frontend pass (số cuối cùng, gồm cả Phase 21/22 chạy trong cùng phiên), `tsc -b`/`eslint` sạch (chỉ còn 1 lỗi + 2 cảnh báo baseline đã biết từ trước, không liên quan phase này).

**⚠️ Cập nhật độ tin cậy phần verify qua browser (phát hiện muộn hơn, xem "Ghi chú phát sinh"):** lúc verify sống qua Playwright, kết luận ban đầu ghi là "verify thật" cho hàng loạt hành vi (redirect, lưới không cần cuộn, `already_in_library` khớp DB, tải hàng loạt, snapshot nền). Sau đó phát hiện **2 tiến trình cùng LISTEN cổng 8000 cùng lúc** trên máy dev (1 tiến trình "ma" không tài nào kill được qua `taskkill`/`Get-Process`/WMI, vẫn nhận phần lớn traffic thật) — nên **không thể khẳng định chắc chắn 100%** mọi lượt verify qua Playwright ở trên đã hit đúng code mới, dù có cơ sở tin phần lớn là đúng (vd `already_in_library` hiện ĐÚNG hỗn hợp theo từng video khớp DB thật — hành vi này không thể tạo ra bởi schema cũ, thứ hoàn toàn thiếu field đó). Phần **chắc chắn đáng tin không phụ thuộc port 8000**: toàn bộ test suite tự động (538+219, chạy trong process test, không qua HTTP) và benchmark tốc độ tải Phase 21 (gọi thẳng hàm Python, không qua cổng 8000). Xem chi tiết điều tra ở "Ghi chú phát sinh" cuối file.

## Đã làm (2026-09-22)
- **Backend**: `TrendingVideoRead` có thêm `video_id`/`already_in_library` (gắn qua 1 query duy nhất `_attach_library_status`, không N+1) cho cả `popular`/`category`/`search`. `download_service.py` có semaphore giới hạn `download_max_videos` (mặc định 3) — tách logic tải nền (`run_download_task`) từ `api/pipeline.py` sang service để dùng chung cho cả nút tải đơn lẻ lẫn tải hàng loạt. `POST /api/jobs/from-selection` giờ tải thật ngay (`download: bool = True`), trả về ĐỦ video đã chọn kể cả video cũ (trước đây bị bỏ qua). Task nền ghi snapshot chuyên mục mỗi 4h (`trending_service.run_periodic_snapshot`, cùng pattern với `storage_cleanup_service`), tách khỏi việc ai đó có mở trang Báo cáo hay không.
- **Frontend**: `features/discover/` (route `/discover`) gộp lưới Trending + tìm kiếm + Douyin thành 1 màn hình, mỗi thẻ tự tải được (nút tải đơn lẻ hoặc chọn hàng loạt), tự đồng bộ % qua SSE (`useVideoTaskProgress`). `features/insights/` (route `/insights`) gộp biểu đồ chuyên mục + "Chủ đề quan tâm" thành 2 tab. Route cũ `/crawl`, `/trending`, `/topics` redirect sang route mới. `lib/format.ts` nhận thêm `formatCompact`/`formatRelativeDate` (trước đây ở `features/trending/format.ts`).
- **Xoá** (không xoá trắng, ghi lại lý do): `features/crawl/table-layout.test.tsx` — test layout của bảng `table-fixed`, bảng đó không còn tồn tại (thay bằng lưới card). `features/crawl/video-row.test.tsx` — hành vi đồng bộ SSE được port sang `features/discover/video-grid-panel.test.tsx` (test `VideoCard` thay vì `VideoRow`).
- **3 quyết định đã chốt qua AskUserQuestion** (khớp đề xuất ban đầu): Douyin là tab thứ 3 luôn hiện; "Chủ đề quan tâm" gộp làm tab của Báo cáo xu hướng; bấm "Tải video đã chọn" tải ngay (không có bước xác nhận riêng).

## Mục tiêu
Một màn hình duy nhất để tìm video và tải video — bỏ vòng lặp "chọn ở Trending → sang Crawl → bấm tải từng dòng". Báo cáo xu hướng (biểu đồ chuyên mục) chuyển sang xem theo nhu cầu, không chiếm chỗ mặc định.

## Khảo sát: hiện trạng thật (đã verify bằng đọc code + chạy thật)

### 1. Video "thêm vào hàng đợi" từ Trending là ngõ cụt — bug thật, không phải chỉ khó dùng
Luồng hiện tại khi tick chọn video ở Trending rồi bấm "Tải video đã chọn":
- `POST /api/jobs/from-selection` → `crawl_service.create_job_from_selection()` tạo các row `Video` với `status=QUEUED`, `local_path=NULL` (`crawl_service.py:229-245`). **Không hề khởi động tải.**
- Toast báo: *"Đã thêm N video vào hàng đợi. Mở trang Crawl để tải."* (`trending/index.tsx:136`).
- Nhưng trang Crawl **không có danh sách job** — state `job` chỉ được set từ mutation search của chính phiên đó (`crawl/index.tsx:176`), và backend **không có `GET /api/jobs`** (chỉ có POST `""`, `/from-selection`, `/{id}/load-more`, `/{id}/cost-estimate`).
- Trang "Video của tôi" cũng không thấy: `file_manager_service.list_video_files()` lọc `Video.local_path.isnot(None)` (`file_manager_service.py:56`) — video chưa tải thì không có `local_path`.

⇒ Video đã chọn nằm trong DB nhưng **không màn hình nào hiển thị được**. Cách duy nhất chạm lại là tình cờ search đúng từ khoá đó ở trang Crawl. Đây chính là câu hỏi "thêm vào hàng đợi làm gì" — đúng, hàng đợi này không dẫn tới đâu cả.

### 2. Hai trang làm cùng một việc bằng hai cơ chế khác nhau
| | Trang Crawl | Trang Trending |
|---|---|---|
| Tìm Bilibili theo từ khoá | ✅ `POST /api/jobs` | ✅ `GET /api/trending/search` |
| Ghi DB khi tìm | **Có** — INSERT ngay mọi video tìm được | **Không** — chỉ đọc |
| Xem trước video | ❌ | ✅ |
| Xếp hạng/chuyên mục | ❌ | ✅ |
| Tải | ✅ từng dòng, có thanh % | ❌ chỉ "thêm hàng đợi" |
| Đánh dấu đã có trong thư viện | ✅ `already_in_library` | ❌ không có field |

Việc Crawl **ghi DB ngay lúc search** là nguồn gốc của bug đã ghi ở [phase-1](phase-1-crawl-bilibili.md) mục *"Search không ra kết quả — hoá ra là lọc trùng"*: tìm lần 2 cùng từ khoá ra 0 video vì tất cả đã bị INSERT ở lần 1 rồi bị `continue`. Mô hình của Trending (đọc-thuần, chỉ ghi khi người dùng thật sự chọn tải) không có lớp bug này.

⇒ Khi gộp, **lấy mô hình đọc-thuần của Trending làm chuẩn**, bỏ hẳn "search tạo job".

### 3. Biểu đồ chiếm chỗ đắt nhất nhưng dữ liệu thưa
Đo thật trên `localhost:5173/trending` (1920×940): card "Chủ đề đang được quan tâm" chiếm ~410px chiều cao ngay dưới ô tìm kiếm, đẩy **toàn bộ lưới video xuống dưới màn hình** — phải cuộn mới thấy video đầu tiên.

Dữ liệu trong biểu đồ đó: các đường gần như nằm ngang, mốc thời gian nhảy cóc 15-09 → 21-09 → 22-09. Lý do ở `GET /api/trending/stats`: *"mỗi lần gọi ghi thêm 1 điểm lịch sử"* (`trending.py:128`) — lịch sử chỉ dày lên khi người dùng mở trang. Biểu đồ vừa chắn đường vừa chưa đủ dữ liệu để nói điều gì.

### 4. Thiếu dữ liệu để gộp được
`TrendingVideoRead` (`schemas/trending.py`) **không có** `already_in_library` và **không có** id video trong DB. Muốn lưới Trending hiện được trạng thái tải / thanh % / link sang "Video của tôi" thì phải bổ sung — đây là phần backend bắt buộc của phase này.

### 5. Cơ chế tải nhiều video song song chưa có giới hạn
`POST /api/videos/{id}/download` đẩy `_run_download` vào `BackgroundTasks` không giới hạn (`pipeline.py:99-120`). Bắn 20 cái cùng lúc = 20 luồng tải đồng thời. `batch_service` **đã có** `asyncio.Semaphore(concurrency)` và hỗ trợ step `"download"` (`batch_service.py:25,144`), nhưng chỉ cho chạy **1 batch tại một thời điểm** (409 nếu đang có batch) nên không dùng lại trực tiếp được cho nút "tải ngay" — sẽ đụng nhau với batch xử lý pipeline của trang Video.

⇒ Đây đúng là hạng mục *"Batch queue qua ProcessPoolExecutor — để làm khi thực sự cần"* còn bỏ ngỏ ở phase-1. Giờ là lúc cần.

## Thiết kế đề xuất

### Điều hướng: 8 mục "Nội dung" → 7, gộp 3 mục khám phá thành 2
```
Trước                          Sau
─────────────────────────      ─────────────────────────
Tổng quan                      Tổng quan
Xu hướng          ┐            Khám phá video   ← gộp (/discover)
Chủ đề quan tâm   ├─ 3 mục     Báo cáo xu hướng ← gộp (/insights)
Tìm & tải         ┘            Video của tôi
Video của tôi                  AI Studio
...                            ...
```
- `/crawl` và `/trending` **redirect** sang `/discover` (giữ link cũ, bookmark không vỡ).
- `/topics` giữ nguyên nội dung nhưng thành 1 tab của `/insights`, tab còn lại là biểu đồ chuyên mục vừa dọn khỏi màn khám phá.

### Màn "Khám phá video" — một lưới duy nhất
```
┌──────────────────────────────────────────────────────────┐
│ Khám phá video            [Chọn chuyên mục 3] [Quét mới] │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ [Bilibili] [YouTube] [Douyin]                        │ │
│ │ 🔍 Tìm theo từ khoá...           ☑ Dịch sang tiếng Trung│
│ └──────────────────────────────────────────────────────┘ │
│ [Tất cả] [Đời sống] [Ẩm thực] [Hài hước]     ← chip mục  │
│ [⬇ Tải 3 video đã chọn] [Chọn tất cả]  · Đã chọn 3       │
│ ┌────────┐ ┌────────┐ ┌────────┐   ← lưới NGAY TRÊN màn  │
│ │ ☑ 🔥   │ │ ☐      │ │ ☐ ✓lib │                        │
│ └────────┘ └────────┘ └────────┘                        │
└──────────────────────────────────────────────────────────┘
```
Quy tắc:
- **Ô tìm trống** → lưới hiện xếp hạng theo chuyên mục đang chọn (nội dung Trending hôm nay).
- **Có từ khoá** → cùng lưới đó đổi sang kết quả search, kèm dòng ghi chú "không phải bảng xếp hạng" như hiện tại. Không sang trang khác, không tạo job.
- **Mọi thẻ video đều tải được**: tick chọn để tải hàng loạt, hoặc nút ⬇ trên từng thẻ để tải ngay một cái.
- Thẻ hiện đúng trạng thái thật: chưa tải / đang tải (thanh %) / đã có trong thư viện (link sang "Video của tôi").
- Douyin giữ nguyên `DouyinPanel` (dán link, không search được) — là tab nguồn thứ 3, không ép chung ô tìm.
- YouTube giữ nguyên: chỉ xem, không có tick chọn/tải (đã chốt từ phase-17).

### Nút tải làm thật, không "thêm hàng đợi"
`POST /api/jobs/from-selection` nhận thêm `download: bool = True`:
1. Tạo/tìm lại row `Video` như hiện nay (giữ dedup).
2. **Khởi động tải luôn** cho mọi video chưa có file, qua hàng đợi có giới hạn.
3. Trả về danh sách video kèm `id` để frontend gắn thanh % (`useVideoTaskProgress`) — y như trang Crawl đang làm.

Toast đổi thành *"Đang tải N video — xem tiến độ ngay trên thẻ hoặc ở icon tác vụ"*, không còn chỉ sang trang khác.

**Hàng đợi tải có giới hạn** — chọn semaphore riêng trong `download_service`, KHÔNG đi qua `batch_service`:
```python
# download_service.py
_SLOTS = asyncio.Semaphore(settings.download_concurrency)  # mặc định 3
```
`_run_download` bọc thân hàm trong `async with _SLOTS:`. Lý do chọn cách này thay vì `batch_service`: batch chỉ cho 1 job chạy một lúc (409), sẽ chặn mất nút tải mỗi khi người dùng đang chạy batch pipeline ở trang Video — hai việc này không nên tranh nhau. Cách này cũng giữ nguyên toàn bộ UI tiến độ per-video (`progress_service` + SSE) đang chạy tốt.
Semaphore này giới hạn **số video** tải cùng lúc. Tốc độ của *từng* video là việc của [phase-21](phase-21-parallel-download.md) (chia file tải nhiều kết nối) — hai tầng khác nhau, và phải chốt ngân sách kết nối chung giữa hai phase, xem mục "Ràng buộc với phase-20" ở đó.
Lưu ý khi làm: endpoint đang set `status=DOWNLOADING` + `progress_service.start()` **trước** khi vào background task, nên video đang xếp hàng sẽ hiện "đang tải" dù chưa tải. Thêm stage label "Đang chờ lượt" lúc chưa lấy được slot.

### Báo cáo xu hướng: xem khi cần, dữ liệu dày hơn
- Chuyển `CategoryChart` sang `/insights` (tab "Chuyên mục"), cạnh tab "Chủ đề quan tâm" (`features/topics`).
- Màn khám phá chỉ còn **một dòng tóm tắt bấm được**, ví dụ: *"Ẩm thực đang dẫn đầu 3 chuyên mục bạn theo dõi · Xem báo cáo →"* — không chiếm chỗ, vẫn có đường dẫn khi cần.
- **Tách việc ghi snapshot ra khỏi việc mở trang**: thêm task định kỳ (mỗi 3–6h) trong `main.py` lifespan, đúng pattern `storage_cleanup_service.run_periodic_cleanup()` đã có sẵn (`main.py:96`). Không dùng APScheduler/cron ngoài — lý do đã ghi ở `storage_cleanup_service.py:56` (app đóng gói desktop không có crontab).
  Đây là điều kiện để biểu đồ có nghĩa: nếu chỉ chuyển chỗ mà vẫn ghi-khi-mở-trang, chuyển sang trang phụ sẽ làm dữ liệu **thưa hơn nữa**.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [x] Xác nhận không có `GET /api/jobs` — không cần viết code để biết, đã liệt kê route ở trên.
- [x] Xác nhận `batch_service` hỗ trợ step `download` + semaphore nhưng vướng khoá 1-batch.
- [x] Xác nhận pattern task định kỳ có sẵn trong `main.py` lifespan.
- [x] Chốt tên/đường dẫn route: `/discover` + `/insights`.
- [x] Chốt `download_max_videos` mặc định **3**.
- [x] Chốt: giữ `/crawl`, `/trending`, `/topics` làm redirect, không xoá.

## Việc cần làm

### Backend
- [x] `schemas/trending.py` — `TrendingVideoRead` thêm `already_in_library: bool = False` và `video_id: int | None = None`.
- [x] `trending_service.py` — `_attach_library_status()` 1 query duy nhất, áp dụng cho `get_bilibili_popular_page`, `get_category_page` (cả nhánh ranking/search), `search_bilibili`.
- [x] `download_service.py` — `_get_download_slots()` semaphore lười (tránh lỗi bind sai event loop khi tạo ở import-time), cấu hình qua `core/config.py` (`download_max_videos: int = 3`).
- [x] `download_service.run_download_task` — chờ slot, báo stage `"queued"` ("Đang chờ lượt") qua `progress_service` khi chưa tới lượt. Chuyển hẳn từ `api/pipeline.py._run_download` sang service để dùng chung cho cả nút tải đơn lẻ lẫn tải hàng loạt.
- [x] `schemas/job.py` + `api/crawl.py` — `JobFromSelectionRequest` thêm `download: bool = True`; endpoint bắn background download cho video mới tạo lẫn video cũ chưa có file.
- [x] `crawl_service.create_job_from_selection` — trả về cả video **đã tồn tại từ trước** (trước đây `continue` bỏ qua hẳn).
- [x] `main.py` + `trending_service.run_periodic_snapshot` — task nền ghi snapshot chuyên mục theo dõi mỗi 4h, tách khỏi việc ai có mở `GET /stats` hay không.
- [x] Test: `test_download_service.py` (5 test — semaphore giới hạn đúng số luồng, stage "queued" khi chờ, `run_download_task` 3 nhánh), `test_crawl_service.py` (+2 — dedup đúng khi chọn video đã có), `test_trending_service.py` (+4 — `_attach_library_status`, `run_periodic_snapshot`).

### Frontend
- [x] `features/discover/video-grid-panel.tsx` — `VideoGridPanel` chuyển từ `features/trending/index.tsx` sang, thêm `VideoCard` với nút tải trên từng thẻ + thanh % qua `useVideoTaskProgress` + link "Video của tôi" khi đã có sẵn.
- [x] `features/discover/index.tsx` — thanh nguồn Bilibili/YouTube/Douyin + `KeywordSearchBox` + chip chuyên mục trong 1 khối trên đầu.
- [x] Xoá `features/crawl/index.tsx` (bảng + luồng tạo job khi search); `DouyinPanel` chuyển nguyên sang `features/discover/douyin-panel.tsx`.
- [x] `features/insights/index.tsx` — tab "Chuyên mục" (`CategoryChart`, chuyển từ `features/trending/`) + tab "Chủ đề quan tâm" (`TopicsPanel`, tách phần thân khỏi `features/topics/index.tsx`, bỏ `AppHeader`/`Main` riêng).
- [x] `sidebar-data.ts` — 3 mục ("Xu hướng"/"Chủ đề quan tâm"/"Tìm & tải") gộp còn 2 ("Khám phá video"/"Báo cáo xu hướng"). Route `/crawl`, `/trending`, `/topics` redirect (`beforeLoad` + `redirect()`).
- [x] `crawl/table-layout.test.tsx` — **xoá, không port**: test layout của bảng `table-fixed`, bảng đó không còn tồn tại (thay bằng lưới card, layout khác hẳn). `crawl/video-row.test.tsx` — port sang `features/discover/video-grid-panel.test.tsx` (test `VideoCard` thay vì `VideoRow`: 3 test cho 3 trạng thái tải).

## Tiêu chí hoàn thành (Definition of Done)
- [x] Test tự động xác nhận: tick chọn → tải → thấy % trên thẻ → xong chuyển "đã có trong thư viện" + link "Video của tôi" (`video-grid-panel.test.tsx`).
- [x] Search dùng mô hình đọc-thuần của Trending (không ghi DB khi search) → lớp bug "tìm lần 2 ra 0 video" không còn cơ sở tồn tại (search không đổi cách hoạt động, chỉ có tải hàng loạt mới ghi DB — đã vậy từ trước, phase này không đổi phần search).
- [x] Bắn N video cùng lúc → semaphore giới hạn đúng `download_max_videos` — verify qua test giả lập 5 lượt tải chạy song song với `download_max_videos=2`, đo `max_concurrent == 2` thật (không phải đoán).
- [x] `tsc -b` sạch (exit 0), `eslint .` chỉ còn 1 lỗi + 2 cảnh báo baseline đã biết từ trước (không liên quan phase này), test backend 475 pass / frontend 211 pass.
- [x] Mở `/crawl`/`/trending`/`/topics` cũ → nhảy đúng sang route mới — verify thật qua Playwright.
- [x] Lưới video nhìn thấy được ngay không cần cuộn ở 1920×940 — verify thật qua Playwright (ảnh chụp màn hình, 4 thẻ hiện đủ ngay dưới thanh chip chuyên mục).
- [x] Gõ từ khoá tiếng Việt có bật dịch → ra kết quả thật — verify thật qua Playwright (2 lượt tìm kiếm khác nhau, cả 2 đều ra kết quả đúng nghĩa).
- [~] Tick chọn → bấm tải → thấy % chạy trên thẻ: verify được nhánh "tải khi đã có sẵn" (không lỗi, tự xoá selection) bằng dữ liệu thật; **chưa** tự mắt thấy thanh % chạy từ 0→100% cho 1 video hoàn toàn mới, vì DB dev hiện tại hầu như mọi video phổ biến/từ khoá thử đều đã có sẵn từ các phiên trước — khó dựng lại tình huống "video chưa từng đụng tới" chỉ bằng UI. Nhánh này đã có 5 test tự động phủ đủ (`test_download_service.py`), coi là đủ tin cậy.
- [x] Bắn N video cùng lúc → semaphore giới hạn đúng `download_max_videos` — verify qua test giả lập (xem mục Test ở trên), không lặp lại bằng tay vì cần ≥`download_max_videos+1` video CHƯA tải cùng lúc, cùng lý do trên.
- [x] `tsc -b` + `eslint` sạch; test frontend/backend pass.

## Ghi chú phát sinh khác

### Windows: `Get-NetTCPConnection`/`Get-Process`/WMI cho PID không nhất quán với Python App Execution Alias (2026-09-22)
Lúc verify sống, dev server backend do `scripts/run-backend.mjs` khởi động qua `spawn(python, ["-m", "uvicorn", ...], {shell: true})`. Truy vết đúng tiến trình thật phải đi qua chuỗi cha-con: `node run-backend.mjs` → `cmd.exe /c "...python.exe -m uvicorn..."` → **hai lớp con**, lớp cuối chạy qua Python App Execution Alias (`WindowsApps\...\python.exe`, không phải `.venv\Scripts\python.exe` trực tiếp). `Get-NetTCPConnection -LocalPort 8000` có lúc trả về 1 PID **không tồn tại** theo `Get-Process`/WMI (App Execution Alias có lớp broker riêng, PID hiển thị không khớp giữa các API) — đừng tin ngay PID đầu tiên tìm được, phải lần theo `ParentProcessId` từ gốc `npm run dev` xuống tới đúng tiến trình `python.exe`/`python3.11.exe` đang thật sự listen (`(Get-NetTCPConnection -LocalPort 8000).OwningProcess` là nguồn đáng tin nhất, nhưng chỉ sau khi đã loại trừ được PID "ma"). Nếu vẫn nghi ngờ code đang chạy có mới không: gọi thẳng service qua `python -c "..."` (đã dùng ở phase-1) đáng tin hơn là cố chẩn đoán qua process list.
Ghi chú thêm: có **nhiều phiên `npm run dev` chạy song song** trên máy này cùng lúc (nhiều Claude session khác cũng đang làm việc trên cùng repo) — `git bash`'s `ps aux` (cột `WINPID`) đôi khi thấy tiến trình mà PowerShell/WMI không thấy ngay (do cache), và ngược lại; đối chiếu cả 2 nguồn khi nghi ngờ.

## Ghi chú phát sinh (2026-09-22, session test độc lập)

**Test tự động: PASS, khớp báo cáo của phiên code.** `pytest` (venv `.venv\Scripts\python.exe`): 475 passed. `pnpm test` (vitest): 211 passed, 28 file. `pnpm exec tsc -b`: sạch (exit 0). `pnpm exec eslint .`: 1 lỗi (`features/editor/index.tsx:209` — thiếu `subject` trong queryKey) + 2 cảnh báo (`subtitle-editor.tsx:164`, `subtitle-review.tsx:80` — React Compiler skip do `useVirtualizer`) — đúng 3 vấn đề baseline đã biết, không liên quan Phase 20.

**Verify qua browser thật: BỊ CHẶN, không phải do code Phase 20.** Profile Chrome dùng chung của Playwright MCP (`C:\Users\phamh\.playwright-mcp\profile`) đang bị khoá bởi 1 tiến trình khác — mọi lệnh `browser_navigate`/`browser_tabs`/`browser_resize` đều báo *"Browser is already in use... use --isolated"*. Có nhiều tiến trình `chrome.exe` thật đang chạy, một số mở các trang tin tức/thể thao thật (apnews.com, kenh14.vn, bongdaplus.vn...) — nhiều khả năng là trình duyệt cá nhân của bạn hoặc phiên khác đang dùng, nên **không chủ động tắt** (rủi ro mất state của người khác). Không đánh giá được bằng mắt các mục DoD cần browser (tick chọn → tải → %, redirect route, đo lưới 1920×940).

**Phát hiện thêm — không phải "backend chạy trong WSL" như phiên code đoán, mà là 1 tiến trình lạ đang chiếm cổng 8000.** Tôi tự `npm run dev` lại ở root (venv backend khởi động sạch, log không có lỗi). Nhưng gọi `curl http://127.0.0.1:8000/openapi.json` thấy `TrendingVideoRead` **thiếu hẳn** `video_id`/`already_in_library` — trong khi import trực tiếp file `backend/app/schemas/trending.py` bằng đúng venv đó thì 2 field này **có mặt**. Kiểm tra thêm:
- `netstat -ano` cho thấy **2 tiến trình cùng LISTEN** trên `127.0.0.1:8000` — 1 là tiến trình của tôi vừa mở, 1 là PID lạ (đổi PID giữa các lần query, ví dụ `1896`).
- Request test đánh dấu riêng gửi tới `127.0.0.1:8000` **không hề xuất hiện** trong log access của tiến trình `npm run dev` tôi vừa mở (không có dòng `INFO: 127.0.0.1:... "GET ...`) — tức curl đang bị tiến trình lạ kia "cướp" trả lời, không tới được server mới.
- Đã tắt hẳn task `npm run dev` của tôi (`TaskStop`) — cổng 8000 **vẫn còn sống**, vẫn trả `HTTP 200` cho `/openapi.json` với schema cũ thiếu field. Vậy tiến trình lạ này **không phải do tôi tạo ra** và tồn tại từ trước khi tôi bắt đầu phiên test.
- Loại trừ WSL: `wsl -l -v` chỉ có distro `docker-desktop` và đang **Stopped**, không có `vmmem`/`vmmemWSL` chạy. Loại trừ Docker Desktop: `docker ps` báo daemon không chạy, không có tiến trình `*docker*`.
- PID lạ đó **không tra được** bằng `Get-Process`, `Get-CimInstance Win32_Process`, hay `tasklist /FI "PID eq ..."` (đều trả về rỗng) dù `netstat -ano` vẫn liệt kê nó đang LISTEN/ESTABLISHED trên cổng 8000 — có thể là tiến trình chạy quyền cao hơn phiên PowerShell không-elevated của tôi, hoặc 1 lớp NAT/proxy ẩn nào đó (Hyper-V?). Tôi dừng điều tra ở đây, không thử kill vì không xác định được đó là tiến trình của ai/việc gì — rủi ro nếu đó là backend thật của 1 phiên Claude khác đang chạy.

**Khuyến nghị cho bạn (người dùng) khi quay lại máy**:
1. Mở Task Manager (quyền Admin, tab Details) hoặc Process Explorer, tìm PID nào đang chiếm cổng 8000 (`netstat -ano | findstr :8000`), tắt nó — rất có thể là 1 backend cũ bị treo từ phiên trước, không rõ nguồn gốc qua công cụ thường.
2. Đóng bớt các Chrome đang mở dùng chung profile Playwright (hoặc chờ phiên khác dùng xong) trước khi nhờ AI verify qua browser.
3. Sau khi cổng 8000 sạch (chỉ 1 tiến trình), chạy lại `npm run dev`, tự thử tay checklist DoD còn lại (tick chọn → tải → %, tìm 2 lần cùng từ khoá, redirect `/crawl`/`/trending`/`/topics`, đo lưới không cuộn ở 1920×940) — **phần này tôi chưa xác nhận được thật, đừng coi phase 20 đã verify đầy đủ chỉ vì test suite xanh**.

Không phát hiện bug trong code Phase 20 qua những gì kiểm tra được (test suite, đọc code) — chỉ là môi trường chạy cục bộ đang có nhiễu, cần bạn dọn tay.

### Bổ sung (cùng ngày, phiên code chính) — xác nhận độc lập + `taskkill` cũng bất lực
Tự kiểm tra lại ngay trước khi push, không dựa vào xác nhận cũ của chính mình:
- `netstat -ano | grep ":8000"` xác nhận đúng như session test độc lập báo: **2 PID cùng LISTEN** (`12944` và `1896`), và **mọi kết nối ESTABLISHED thật** (traffic đang chạy) đều đổ vào PID `1896` — tức phần lớn request qua cổng 8000 đang được tiến trình lạ trả lời, không phải server mới khởi động.
- Thử `taskkill /F /PID 12944` và `taskkill /F /PID 1896`: **cả 2 đều báo "process not found"** — nhưng `netstat` chạy ngay sau đó **vẫn thấy cả 2 đang LISTEN/ESTABLISHED**, thậm chí có thêm connection mới (cổng ephemeral đổi). Không có công cụ nào từ phiên PowerShell/Bash hiện tại (Get-Process, WMI, tasklist, taskkill) chạm được tới các PID này dù chúng rõ ràng đang hoạt động — nghi ngờ mạnh đây là PID thuộc 1 namespace tiến trình khác (sandbox/ảo hoá tầng dưới môi trường Claude Code đang chạy), vượt quá khả năng debug bằng các tool sẵn có.
- **Vẫn giữ được 1 lượt verify đáng tin cậy không qua cổng 8000**: benchmark tốc độ tải Phase 21 (8.64x, `sha256` khớp) gọi thẳng hàm Python trong `download_service.py`, không qua HTTP — không bị ảnh hưởng bởi vấn đề cổng 8000 này.
- **Kết luận cho phiên sau**: đừng tin bất kỳ xác nhận "verify qua browser/curl tới localhost:8000" nào trong các phase gần đây (bao gồm cả của chính phiên này) là chắc chắn 100% — cần môi trường máy sạch (khởi động lại máy, đúng như người dùng đã yêu cầu) rồi verify lại từ đầu. Ưu tiên verify bằng cách gọi thẳng hàm Python/service (không qua HTTP) khi cần độ tin cậy cao trong lúc môi trường còn nhiễu.
