# Phase 1: Crawl & Trend Discovery (Bilibili)

Trạng thái: **Backend xong & verify bằng API thật** — Frontend UI (trang Crawl/Trend, dọn Clerk/demo pages) và merge ffmpeg thật chưa làm, xem Ghi chú.

## Mục tiêu
Crawl video Bilibili theo từ khoá, tải không watermark, dedup, batch queue cơ bản. Trang Trend Discovery hiển thị video/ranking phổ biến Bilibili để chọn từ khoá crawl.

## Phạm vi
**Trong phạm vi:** search theo keyword, tải video (merge DASH bằng ffmpeg), lưu file theo `job_id/video_id/`, dedup theo video ID, adapter Trend Discovery (popular + ranking/region), lưu snapshot trending vào DB, batch queue qua `ProcessPoolExecutor`.

**Ngoài phạm vi:** Douyin, AI pipeline (transcribe/dịch/TTS), phụ đề, tách nhạc nền.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [x] Endpoint search theo keyword: **cần WBI signing** (Bilibili đã chặn endpoint search cũ không ký) — đã cài đặt cơ chế ký (`app/adapters/bilibili/wbi.py`) và verify chạy được bằng request thật.
- [ ] Chọn danh sách `rid` (region id, vd Anime/Game/Life...) muốn theo dõi cho Trend Discovery — hiện API `ranking()` nhận `rid` tuỳ ý qua query param, chưa cố định danh sách category hiển thị mặc định trên UI (chưa có UI).
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
- [ ] Trang UI: tạo job crawl theo keyword, xem kết quả, xem trending, nút "Dùng làm từ khoá crawl" — **chưa làm**, cần dọn Clerk + demo pages trong `frontend/` trước (ghi chú từ Phase 0) rồi mới dựng trang thật.
- [ ] Batch queue qua `ProcessPoolExecutor` cho nhiều video cùng lúc — hiện `download_bilibili_video()` mới chạy tuần tự/đơn lẻ qua API, chưa có hàng đợi giới hạn concurrency.

## Tiêu chí hoàn thành (Definition of Done)
- [x] Nhập 1 từ khoá → tool trả về danh sách video Bilibili thật — verify qua `POST /api/jobs` với keyword thật, nhận về video thật kèm bvid/title/author/duration.
- [ ] Tải được ít nhất 1 video về máy, không dính watermark, phát được bằng trình phát video thông thường — **bị chặn bởi thiếu ffmpeg trên máy**, code đã sẵn sàng (`download_service.download_bilibili_video`), chỉ cần cài ffmpeg rồi gọi thử.
- [x] Xem được danh sách trending Bilibili theo category — verify qua `GET /api/trending/bilibili/popular` và `/ranking?rid=1&day=3`, trả về dữ liệu thật.
- [x] Chạy lại cùng từ khoá không tải trùng video đã có — verify: gọi 2 lần liên tiếp cùng keyword, không có lỗi `UniqueConstraint` (nếu dedup sai sẽ crash 500 ở lần 2), dedup hoạt động đúng dù kết quả search Bilibili tự thay đổi thứ tự/nội dung giữa 2 lần gọi (bản chất search API, không phải bug).

## Ghi chú phát sinh trong lúc làm
- **Bilibili đã chặn endpoint search cũ** (`x/web-interface/search/type`) — verify bằng request thật, giờ trả về trang lỗi HTML thay vì JSON. Bắt buộc dùng endpoint WBI-signed (`x/web-interface/wbi/search/all/v2`). Cơ chế WBI: lấy `img_key`+`sub_key` từ `nav`, trộn qua 1 bảng hoán vị cố định thành `mixin_key`, rồi md5-sign query string kèm timestamp. Đã cài trong `wbi.py`, cache key ~6h vì Bilibili đổi key theo ngày.
- `x/player/wbi/playurl` cũng cần WBI sign (không phải chỉ search).
- `x/web-interface/popular` và `x/web-interface/ranking/region` **không cần** WBI sign — verify thực tế cả 2 chạy OK không ký.
- Response `duration` field không đồng nhất giữa các endpoint: search trả `"mm:ss"` (string), ranking trả số giây thuần — đã chuẩn hoá qua `_parse_duration_to_seconds()` ở cả 2 service.
- Title từ search API đôi khi bọc `<em class="keyword">` quanh từ khớp — đã strip trong `client.py`.
- Model `Job`/`Video` ban đầu thiếu quan hệ SQLAlchemy `relationship()` hai chiều — Pydantic `model_validate(job, from_attributes=True)` không tự suy ra field `videos` nếu không có `relationship`. Đã thêm `Job.videos` / `Video.job` (back_populates) — nhớ pattern này khi thêm quan hệ DB mới ở phase sau.
- Bilibili search API trả kết quả **không ổn định giữa các lần gọi** cùng 1 keyword (thứ tự/nội dung xê dịch, có vẻ do cá nhân hoá/xoay vòng phía server) — không phải lỗi code, cần nhớ khi viết test/debug dựa vào "gọi 2 lần phải giống hệt nhau".
- **Chưa test được bước tải + merge ffmpeg thật** vì máy chưa cài ffmpeg — `ensure_ffmpeg_available()` sẽ raise `FfmpegNotFoundError` sớm nếu gọi khi chưa cài, không tải phí công. Việc cần làm khi có ffmpeg: gọi thử `download_service.download_bilibili_video()` với 1 bvid/cid thật, xác nhận file `original.mp4` phát được.
- **Frontend chưa động tới** ở phase này — ưu tiên xong backend + verify API thật trước. Việc dọn Clerk/demo pages (đã ghi ở Phase 0) và dựng trang Crawl/Trend thật nên làm ở phiên kế tiếp, không gộp chung để giữ mỗi phiên gọn (theo quy tắc tiết kiệm token trong CLAUDE.md).
