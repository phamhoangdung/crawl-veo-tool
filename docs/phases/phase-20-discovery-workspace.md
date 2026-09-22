# Phase 20: Gộp "Xu hướng" + "Tìm & tải" thành một màn Khám phá

Trạng thái: **Đã khảo sát & lên kế hoạch, chưa code** (2026-09-22).

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
- [ ] Chốt tên/đường dẫn route: `/discover` + `/insights` (hay tên tiếng Việt khác).
- [ ] Chốt `download_concurrency` mặc định (đề xuất **3** — mỗi video Bilibili ~200–400MB, 3 luồng đủ no băng thông mà không làm treo UI).
- [ ] Chốt: có giữ `/crawl`, `/trending` làm redirect vĩnh viễn hay xoá hẳn sau 1 thời gian.

## Việc cần làm

### Backend
- [ ] `schemas/trending.py` — `TrendingVideoRead` thêm `already_in_library: bool = False` và `video_id: int | None = None`.
- [ ] `trending_service.py` — sau khi dựng danh sách video, 1 query duy nhất theo `platform_video_id IN (...)` để gắn 2 field trên (đúng pattern chống N+1 đã dùng ở `create_job_from_selection`). Áp dụng cho cả `get_popular_page`, `get_category_page`, `search_bilibili`.
- [ ] `download_service.py` — thêm `_SLOTS = asyncio.Semaphore(...)`, cấu hình qua `core/config.py` (`download_concurrency: int = 3`).
- [ ] `api/pipeline.py` — `_run_download` chờ slot; báo "Đang chờ lượt" qua `progress_service` khi chưa tới lượt.
- [ ] `schemas/job.py` + `api/crawl.py` — `JobFromSelectionRequest` thêm `download: bool = True`; endpoint bắn background download cho các video mới tạo.
- [ ] `crawl_service.create_job_from_selection` — trả về cả video **đã tồn tại từ trước** (hiện đang `continue` bỏ qua hẳn), để frontend biết cái nào "đã có rồi" thay vì im lặng biến mất khỏi kết quả.
- [ ] `main.py` — đăng ký task định kỳ ghi snapshot chuyên mục đang theo dõi; tách phần ghi snapshot khỏi `GET /stats` (hoặc giữ nhưng chặn ghi trùng trong khoảng ngắn).
- [ ] Test: dedup vẫn đúng khi chọn video đã có; semaphore giới hạn đúng số luồng; `already_in_library` đúng với DB thật.

### Frontend
- [ ] `features/discover/` mới — chuyển `VideoGridPanel` từ `features/trending/index.tsx` sang dùng chung, bổ sung: nút tải trên từng thẻ, badge trạng thái, thanh % qua `useVideoTaskProgress`.
- [ ] Thanh nguồn Bilibili/YouTube/Douyin + `KeywordSearchBox` (đã là component chung) + chip chuyên mục trong một khối dính trên đầu.
- [ ] Bỏ `features/crawl/index.tsx` (bảng + luồng tạo job khi search); giữ `DouyinPanel`, `VideoRow` thì rã ra lấy phần đồng bộ trạng thái SSE.
- [ ] `features/insights/` — tab "Chuyên mục" (`CategoryChart`) + tab "Chủ đề quan tâm" (`features/topics` hiện tại).
- [ ] `sidebar-data.ts` — đổi 3 mục thành 2; route `/crawl`, `/trending`, `/topics` redirect.
- [ ] Giữ nguyên test đang có ở `crawl/table-layout.test.tsx`, `crawl/video-row.test.tsx` — chuyển sang màn mới hoặc thay bằng test tương đương cho lưới, **không xoá trắng**.

## Tiêu chí hoàn thành (Definition of Done)
- [ ] Từ màn Khám phá: tick 3 video đang hot → bấm tải → **thấy % chạy ngay trên thẻ** → xong thì thẻ chuyển "đã có trong thư viện" và mở được ở "Video của tôi". Không phải sang trang nào khác. Verify bằng video Bilibili thật.
- [ ] Gõ từ khoá tiếng Việt có bật dịch → ra kết quả → tải được 1 video từ chính kết quả đó.
- [ ] Tìm lại cùng từ khoá lần 2 **vẫn ra đủ kết quả** (không còn lớp bug "ra 0 video" vì search không còn ghi DB).
- [ ] Bắn 10 video cùng lúc → đo thật chỉ có ≤3 tiến trình tải chạy song song, số còn lại xếp hàng và lần lượt chạy hết.
- [ ] Mở `/crawl`, `/trending` cũ → nhảy đúng sang màn mới.
- [ ] Lưới video nhìn thấy được ngay **không cần cuộn** ở 1920×940 (đo bằng Playwright như lần đo hiện trạng).
- [ ] `tsc -b` + `eslint` sạch; test frontend/backend pass.

## Câu hỏi cần bạn chốt trước khi code
1. **Douyin đặt đâu?** Đề xuất làm tab nguồn thứ 3 trong màn Khám phá. Nó đang BLOCKED (thiếu tài khoản, xem phase-3) nên cũng có thể tạm ẩn khỏi màn chính cho gọn.
2. **"Chủ đề quan tâm" có gộp vào Báo cáo không?** Đề xuất có (cùng bản chất "xem để quyết định làm gì"). Nếu bạn dùng nó thường xuyên như một việc riêng thì nên để nguyên mục sidebar.
3. **Tự động tải sau khi chọn** — luôn tải ngay, hay để nút tách đôi "Chọn xong / Tải ngay"? Đề xuất tải ngay, vì "chọn mà không tải" chính là cái hàng đợi vô nghĩa đang bị than phiền.
