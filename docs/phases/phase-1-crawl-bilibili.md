# Phase 1: Crawl & Trend Discovery (Bilibili)

Trạng thái: **Xong** (trừ batch queue giới hạn concurrency — xem "Việc cần làm"). Backend + trang UI Crawl/Trending đã verify chạy đúng qua Playwright với API thật.

## Mục tiêu
Crawl video Bilibili theo từ khoá, tải không watermark, dedup, batch queue cơ bản. Trang Trend Discovery hiển thị video/ranking phổ biến Bilibili để chọn từ khoá crawl.

## Phạm vi
**Trong phạm vi:** search theo keyword, tải video (merge DASH bằng ffmpeg), lưu file theo `job_id/video_id/`, dedup theo video ID, adapter Trend Discovery (popular + ranking/region), lưu snapshot trending vào DB, batch queue qua `ProcessPoolExecutor`.

**Ngoài phạm vi:** Douyin, AI pipeline (transcribe/dịch/TTS), phụ đề, tách nhạc nền.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [x] Endpoint search theo keyword: **cần WBI signing** (Bilibili đã chặn endpoint search cũ không ký) — đã cài đặt cơ chế ký (`app/adapters/bilibili/wbi.py`) và verify chạy được bằng request thật.
- [x] Danh sách category theo dõi: **Giải trí (rid 71), Ẩm thực (rid 211), Đời sống (rid 21)** — verify đúng qua field `typename` trả về từ request thật (71→综艺, 211→美食记录, 21→日常). Expose qua `GET /api/trending/bilibili/categories`.
- [x] Không cần video mẫu cố định — service tự lấy bvid/cid thật từ chính kết quả search/trending để test.
- [x] Xác nhận cookie: **không cần cookie đăng nhập** cho search/popular/ranking/playurl — đã verify DASH trả về tới chất lượng 1080P60 (quality 116) mà không cần SESSDATA. Có thể cần cookie sau này nếu muốn quality cao hơn hoặc gặp rate-limit.

Endpoint đã dùng thật (xác nhận hoạt động qua request thật tới `api.bilibili.com`):
- `GET /x/web-interface/nav` — lấy `img_key`/`sub_key` để tính WBI mixin key.
- `GET /x/web-interface/wbi/search/all/v2?search_type=video&keyword=...` (WBI-signed) — search theo keyword.
- `GET /x/web-interface/popular?pn=&ps=` — video phổ biến (không cần ký).
- `GET /x/web-interface/ranking/region?rid=&day=` — bảng xếp hạng theo phân khu (không cần ký).
- `GET /x/player/wbi/playurl?bvid=&cid=&fnval=16` (WBI-signed) — lấy DASH video/audio stream để tải.

## Việc cần làm
- [x] `app/adapters/bilibili/wbi.py` — ký WBI (cache mixin key ~6h).
- [x] `app/adapters/bilibili/client.py` (`BilibiliClient`) — `search_videos()`, `get_popular()`, `get_ranking()`, `get_play_streams()`. Có strip tag `<em>` Bilibili hay chèn vào title khi search.
- [x] `app/adapters/ffmpeg.py` — `merge_video_audio()` + `ensure_ffmpeg_available()` (check sớm trước khi tải, tránh tải xong mới báo lỗi thiếu ffmpeg).
- [x] `app/services/crawl_service.py` — search + dedup (theo `UniqueConstraint(platform, platform_video_id)`) + lưu Job/Video.
- [x] `app/services/trending_service.py` — map response Bilibili sang `TrendingVideoRead`.
- [x] `app/services/download_service.py` — tải video-only + audio-only stream rồi merge bằng ffmpeg (chưa test thật vì máy chưa có ffmpeg, xem Ghi chú).
- [x] API: `POST /api/jobs` (tạo job crawl + trả job kèm videos), `GET /api/trending/bilibili/popular`, `GET /api/trending/bilibili/ranking`.
- [x] Test mocked (`tests/adapters/test_bilibili_client.py`, dùng `httpx.MockTransport`, không gọi mạng thật) — 5/5 pass.
- [x] Dọn demo pages `chats/tasks/apps/users` trong `frontend/` (route + feature), thay nav sidebar bằng "Crawl"/"Trending".
- [x] `frontend/src/lib/api.ts` — axios client dùng `VITE_API_BASE_URL`, type cho Job/Video/Trending.
- [x] Trang `features/crawl/index.tsx` + route `/crawl`: form nhập từ khoá → gọi `POST /api/jobs` → bảng kết quả (tiêu đề/tác giả/thời lượng/trạng thái).
- [x] Trang `features/trending/index.tsx` + route `/trending`: tabs theo category (từ `GET /api/trending/bilibili/categories`) → lưới card video theo `GET /api/trending/bilibili/ranking?rid=`.
- [x] Verify cả 2 trang bằng Playwright thật (không chỉ code review): nhập từ khoá thật, nhận kết quả thật; chuyển tab category, xem đúng dữ liệu thật.
- [ ] Batch queue qua `ProcessPoolExecutor` cho nhiều video cùng lúc — hiện `download_bilibili_video()` mới chạy tuần tự/đơn lẻ qua API, chưa có hàng đợi giới hạn concurrency. Để làm khi thực sự cần chạy nhiều video song song (chưa cấp thiết ở quy mô test hiện tại).

## Tiêu chí hoàn thành (Definition of Done)
- [x] Nhập 1 từ khoá → tool trả về danh sách video Bilibili thật — verify qua `POST /api/jobs` với keyword thật, nhận về video thật kèm bvid/title/author/duration.
- [x] Tải được ít nhất 1 video về máy, không dính watermark — **đã cài ffmpeg (winget, Gyan.FFmpeg) và test thật**: tải + merge 1 video Bilibili thật (436MB) qua `download_service.download_bilibili_video()`, ra file `original.mp4` hợp lệ. Lưu ý: winget cập nhật PATH hệ thống vĩnh viễn, nhưng session/terminal đang mở cần mở lại mới thấy `ffmpeg` trong PATH (đã verify bằng cách trỏ thẳng path cài đặt trong lúc test).
- [x] Xem được danh sách trending Bilibili theo category — verify qua `GET /api/trending/bilibili/popular` và `/ranking?rid=1&day=3`, trả về dữ liệu thật.
- [x] Chạy lại cùng từ khoá không tải trùng video đã có — verify: gọi 2 lần liên tiếp cùng keyword, không có lỗi `UniqueConstraint` (nếu dedup sai sẽ crash 500 ở lần 2), dedup hoạt động đúng dù kết quả search Bilibili tự thay đổi thứ tự/nội dung giữa 2 lần gọi (bản chất search API, không phải bug).

## Ghi chú phát sinh trong lúc làm

### Search hiện đủ kết quả Bilibili, cache chỉ dùng cho từ khoá (2026-09-08)
- Chốt hướng: kết quả search phải là **đúng những gì Bilibili trả về**, không lọc bớt. Video đã có trong thư viện vẫn hiện, chỉ đánh dấu `already_in_library` (theo từng video) để không tải lại.
- **KHÔNG gán vào `job.videos`**: đó là quan hệ SQLAlchemy — gán vào sẽ dời `job_id` của video cũ sang job mới và làm mất liên kết với job gốc. Đã thử và xác nhận phá dữ liệu, nên dùng thuộc tính tạm `job.result_videos` + `AliasChoices` ở schema.
- Chỉ INSERT video chưa có: bảng `videos` có `UniqueConstraint(platform, platform_video_id)`.
- Trạng thái không đủ để suy ra "đã có": video đã tải mà chưa xử lý vẫn là `queued` — phải có cờ riêng.
- Cache từ khoá đã dịch chuyển từ RAM (TTL 1h, mất khi restart) sang bảng `translation_cache`. Verify: xoá cache RAM rồi gọi lại vẫn chỉ 1 lần gọi API.

### "Search không ra kết quả" — hoá ra là lọc trùng (2026-09-08)
- Triệu chứng: cùng từ khoá, lần trước ra 19-40 video, lần sau ra **0 video**. Nghi Bilibili chặn, nhưng đo thật thì API vẫn trả 20 video ở mọi trang (1→30) và cả khi bắn 12 request dồn dập — **không phải risk control**.
- Nguyên nhân: `create_bilibili_crawl_job` bỏ qua video đã có trong DB (`continue`). Bilibili trả gần như cùng một tập video cho mỗi lần tìm, nên khi đã tải hết thì job mới rỗng. Đo thật: 20/20 video đã có trong DB (tổng 308 video Bilibili).
- Vấn đề thực sự là **UI im lặng**: hiện "0 video" y như không tìm thấy gì. Đã thêm `skipped_existing` / `total_found` (cờ tạm, không lưu DB — cùng cách với `translation_failed`) và khối giải thích kèm nút "Tải thêm trang sau" / "Xem thư viện".
- Ẩn luôn bảng khi rỗng: trước đó chỉ còn hàng tiêu đề trơ trọi.

### Tooltip xem ảnh to + dịch tiêu đề (2026-09-08)
- Thumb trong bảng phải nhỏ để vừa nhiều dòng, nhưng nhỏ thì không thấy nội dung video → `ThumbPreview` hover hiện ảnh 320px. **Không bọc tooltip khi thumb nằm trong `<Link>`**: `<button>` lồng trong `<a>` là HTML không hợp lệ và làm hỏng điều hướng (đã thử ở trang Quản lý file rồi bỏ).
- `TranslatedTitle` hover hiện bản dịch tiếng Việt, **dịch lười — chỉ gọi khi tooltip mở thật**. Dịch sẵn cả trang là đốt quota cho 40 tiêu đề mà người dùng chỉ xem vài dòng. Bỏ qua luôn tiêu đề không có ký tự Hán.
- **Cache 2 tầng**: `queryKey: ['translate', title]` (TanStack Query, dùng chung giữa các dòng trùng tiêu đề) + bảng `translation_cache` ở backend (bền qua restart). Khoá cache theo **hash nội dung text**, không theo video id — video re-up rất hay trùng tiêu đề, và text dài hơn giới hạn index của SQLite nên phải hash.
- `POST /api/translate/batch` bỏ trùng trước khi dịch; hết quota giữa lô thì trả về phần đã dịch được và dừng, không đốt thêm request.
- Verify: 4 request → 2 lần gọi API thật; test kiểm chứng chạy đỏ khi gỡ điều kiện "chỉ khi hover" và khi phá cache dùng chung (329 lần gọi thay vì 1).

- **Bilibili đã chặn endpoint search cũ** (`x/web-interface/search/type`) — verify bằng request thật, giờ trả về trang lỗi HTML thay vì JSON. Bắt buộc dùng endpoint WBI-signed (`x/web-interface/wbi/search/all/v2`). Cơ chế WBI: lấy `img_key`+`sub_key` từ `nav`, trộn qua 1 bảng hoán vị cố định thành `mixin_key`, rồi md5-sign query string kèm timestamp. Đã cài trong `wbi.py`, cache key ~6h vì Bilibili đổi key theo ngày.
- `x/player/wbi/playurl` cũng cần WBI sign (không phải chỉ search).
- `x/web-interface/popular` và `x/web-interface/ranking/region` **không cần** WBI sign — verify thực tế cả 2 chạy OK không ký.
- Response `duration` field không đồng nhất giữa các endpoint: search trả `"mm:ss"` (string), ranking trả số giây thuần — đã chuẩn hoá qua `_parse_duration_to_seconds()` ở cả 2 service.
- Title từ search API đôi khi bọc `<em class="keyword">` quanh từ khớp — đã strip trong `client.py`.
- Model `Job`/`Video` ban đầu thiếu quan hệ SQLAlchemy `relationship()` hai chiều — Pydantic `model_validate(job, from_attributes=True)` không tự suy ra field `videos` nếu không có `relationship`. Đã thêm `Job.videos` / `Video.job` (back_populates) — nhớ pattern này khi thêm quan hệ DB mới ở phase sau.
- Bilibili search API trả kết quả **không ổn định giữa các lần gọi** cùng 1 keyword (thứ tự/nội dung xê dịch, có vẻ do cá nhân hoá/xoay vòng phía server) — không phải lỗi code, cần nhớ khi viết test/debug dựa vào "gọi 2 lần phải giống hệt nhau".
- ~~Chưa test được bước tải + merge ffmpeg thật~~ **Đã test xong**: cài ffmpeg qua `winget install Gyan.FFmpeg`, gọi `download_service.download_bilibili_video()` với bvid/cid thật (lấy từ chính `get_popular()`), ra file `original.mp4` 436MB hợp lệ, không lỗi.
- **Bug đã sửa**: CORS backend cố định `allow_origins=["http://localhost:5173"]` — Vite tự đổi cổng (5174, 5175...) khi 5173 bận (hay gặp lúc dev vì tiến trình cũ chưa dọn sạch), khiến browser bị chặn CORS dù backend chạy đúng. Sửa thành `allow_origin_regex=r"http://localhost:\d+"` (chấp nhận mọi cổng localhost — chỉ hợp lý vì đây là tool chạy local, không expose ra ngoài).
- **Lưu ý vận hành `--reload`**: gặp trường hợp `uvicorn --reload` báo "WatchFiles detected changes... Reloading..." nhưng worker process cũ (`--multiprocessing-fork`) không thực sự bị thay, vẫn phục vụ code cũ — nếu sửa code mà hành vi không đổi dù server "đã reload", kiểm tra lại bằng cách tắt hẳn qua `Get-CimInstance Win32_Process | Where Name -match python` (tìm đúng PID `--multiprocessing-fork`, không phải PID reloader) rồi khởi động lại sạch, đừng cố đoán/sửa code thêm.
- **Trending category "Giải trí" (rid 71) chỉ trả về 1 video** từ `ranking/region` (so với 9-11 video ở rid 21/211) — verify là dữ liệu thật từ Bilibili tại thời điểm test, không phải lỗi code. Nếu muốn nhiều nội dung giải trí hơn, có thể cân nhắc đổi/thêm rid khác cho category này ở phase sau.

## Bổ sung sau (phiên 2026-09-07)

- **Tải video từ Trending**: `POST /api/jobs/from-selection` nhận danh sách video người dùng tick chọn (metadata gửi kèm từ frontend, không gọi lại API Bilibili). Trang Trending có checkbox trên từng card + nút "Chọn tất cả".
- **Dịch từ khoá sang tiếng Trung**: `JobCreateRequest.translate_keyword` (mặc định UI bật sẵn). Bilibili là nền tảng Trung Quốc nên search nguyên văn tiếng Việt gần như không ra kết quả. Dùng lại `translate_service.translate_text` (OpenAI → fallback Google free), bỏ qua nếu từ khoá đã là tiếng Trung, và **fallback về từ khoá gốc nếu dịch lỗi** — dịch hỏng không được làm chết cả job. Verify thật: `'ẩm thực'` → `'美食'`.
- **Ảnh thumbnail**: thêm cột `videos.cover_url` (search API trả field `pic`, dạng `//i2.hdslb.com/...` thiếu scheme → chuẩn hoá về https). Hiển thị ở cả trang Crawl (cột Ảnh) lẫn Trending.
- **Hotlink**: Bilibili chặn ảnh theo header `Referer` (gửi kèm localhost → 403). Frontend dùng `referrerPolicy="no-referrer"`; có thêm `/api/image` proxy ở backend làm fallback khi CDN siết chặt (chỉ cho phép host `.hdslb.com`/`.bilibili.com` để tránh SSRF).
- **Migration**: dự án chưa dùng Alembic mà `create_all()` không sửa bảng cũ, nên thêm `ensure_schema_columns()` trong `app/core/db.py` — tự `ALTER TABLE ADD COLUMN` cho cột nullable còn thiếu, chạy lúc startup. Khi schema thay đổi nhiều hơn thì nên chuyển sang Alembic.

### Trending: chọn chuyên mục, phân trang, chart (phiên 2026-09-07)

**Ràng buộc API Bilibili (đo thật, quan trọng khi sửa sau này):**
- `ranking/region` trả **~11 video/category và KHÔNG phân trang** (không có tham số `pn`).
- `popular` **có** phân trang (20/trang) nhưng là bảng xếp hạng chung, không chia category. Cần header User-Agent, thiếu thì trả `code: -352` (risk control).
- `search/all/v2` có phân trang thật — đây là nguồn duy nhất để lướt sâu theo chủ đề.
- Item ranking **không có** field lượt thích; dùng `favorites` (lượt lưu) làm chỉ số tương tác.

**Đã làm:**
- **Chọn chuyên mục**: `app/services/bilibili_categories.py` liệt kê 39 category (rid + tên Việt + tên Trung + nhóm), tất cả xác nhận bằng request thật. `GET /categories` trả toàn bộ, `GET /default-categories` trả 3 mục mặc định. UI có Sheet chọn nhiều mục + ô tìm kiếm, lưu lựa chọn vào `localStorage`.
- **Infinite scroll (Trending)**: `GET /category-page?rid&page` — **trang 1 lấy từ ranking** (đúng nghĩa "đang hot"), **trang sau lấy từ search theo `name_zh`** của category. Frontend lọc trùng bvid giữa 2 nguồn. Cache `staleTime` 5 phút để chuyển tab qua lại không gọi lại API.
- **Infinite scroll (Crawl)**: `POST /api/jobs/{id}/load-more?page=N` — search thêm bằng chính `job.keyword` (đã dịch nếu bật) rồi thêm video vào job, bỏ qua video đã có trong DB.
- **Chart**: `GET /stats?rids=1,2,3` gọi song song từng category, trả tổng/trung bình/max lượt xem + lượt lưu + video nổi nhất, sắp giảm dần theo tổng lượt xem. Category lỗi bị bỏ qua chứ không làm hỏng cả biểu đồ. UI vẽ bar chart ngang bằng recharts (đã có sẵn trong deps).
- Hook dùng chung `frontend/src/hooks/use-infinite-scroll.ts` (IntersectionObserver, dùng state chứ không phải ref để effect chạy lại khi sentinel gắn vào DOM).

**Chưa làm**: theo dõi xu hướng theo thời gian (tăng/giảm) — Bilibili chỉ trả snapshot hiện tại, muốn có đường xu hướng phải tự lưu snapshot vào DB theo ngày rồi so sánh.

### Chuyên mục động, chart xu hướng, theo dõi tải (phiên 2026-09-07, phần 3)

**Chuyên mục lấy từ API thay vì hardcode** — `bilibili_categories.py` đã bị xoá.
- Bilibili **không có** endpoint trả cây phân loại, nhưng mọi API video đều kèm `tid`/`tname`. `category_service.discover_categories()` quét `popular` (2 trang) + `online/list` để dựng danh sách thật → **40 chuyên mục** thay vì 39 mục tự điền, và tự bắt kịp khi Bilibili thêm mục mới.
- Bảng `categories` (rid, name_zh, name_vi, group_name, is_followed, first/last_seen_at). Tên tiếng Việt dịch dần qua `translate_missing_names()` (mỗi lần 20 mục) — mục chưa dịch vẫn dùng được, UI hiển thị tên tiếng Trung.
- Nhóm được đoán bằng từ khoá trong tên tiếng Trung (`_GROUP_HINTS`), không khớp thì để None → UI xếp vào "Khác".
- Lựa chọn theo dõi lưu ở **DB** (`is_followed`), không phải localStorage — chuẩn bị cho việc đóng gói thành app desktop.
- Lưu ý đã gặp: rid của cùng một mục có thể khác giữa các API (`211` vs `215` đều là 美食记录) — thêm lý do không nên hardcode.

**Chart dạng line theo thời gian**
- Bilibili chỉ trả snapshot hiện tại nên phải **tự tích luỹ**: bảng `category_snapshots` ghi 1 điểm mỗi lần gọi `/stats`, chống ghi dày bằng `min_interval_minutes=30`.
- `GET /history?rids&days` trả chuỗi điểm để vẽ. Khi chưa đủ 2 điểm, UI hiển thị thanh ngang số liệu hiện tại kèm giải thích — không vẽ đường giả.
- `heat_score` = lượt xem trung bình / số ngày xếp hạng, để so sánh được giữa các khung `day` khác nhau.

**Theo dõi tiến độ tải (trang Crawl)**
- `progress_service` giữ tiến độ **trong bộ nhớ** (dict + Lock), không ghi DB: tiến độ chỉ có nghĩa lúc đang tải, mất khi restart là đúng. **Nếu sau này chuyển sang Celery/nhiều worker thì phải đổi sang Redis.**
- Chặng: pending → video → audio → merging → done/failed. Mỗi chặng đếm lại byte từ đầu, nên phần trăm là của chặng hiện tại chứ không phải toàn bộ.
- `GET /api/downloads/progress` (frontend poll 800ms khi còn mục đang tải, dừng hẳn khi rỗng), `DELETE /progress/{id}` để bỏ mục đã xong.
- `GET /api/downloads/location` cho biết file lưu ở đâu; `POST /api/downloads/reveal` mở Finder/Explorer (macOS `open -R`, Windows `explorer /select,`, Linux `xdg-open`). **Đường dẫn luôn lấy từ DB, không nhận từ client** — nếu không endpoint này thành công cụ mở file tuỳ ý trên máy.
