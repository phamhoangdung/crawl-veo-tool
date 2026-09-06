# Phase 1: Crawl & Trend Discovery (Bilibili)

Trạng thái: Chưa bắt đầu (phụ thuộc Phase 0)

## Mục tiêu
Crawl video Bilibili theo từ khoá, tải không watermark, dedup, batch queue cơ bản. Trang Trend Discovery hiển thị video/ranking phổ biến Bilibili để chọn từ khoá crawl.

## Phạm vi
**Trong phạm vi:** search theo keyword, tải video (merge DASH bằng ffmpeg), lưu file theo `job_id/video_id/`, dedup theo video ID, adapter Trend Discovery (popular + ranking/region), lưu snapshot trending vào DB, batch queue qua `ProcessPoolExecutor`.

**Ngoài phạm vi:** Douyin, AI pipeline (transcribe/dịch/TTS), phụ đề, tách nhạc nền.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [ ] Tra cứu endpoint search theo keyword của Bilibili cụ thể trong [SocialSisterYi/bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect) (chưa tra ở giai đoạn lập plan, cần làm đầu phase này).
- [ ] Chọn danh sách `rid` (region id, vd Anime/Game/Life...) muốn theo dõi cho Trend Discovery.
- [ ] 1 URL video Bilibili mẫu cụ thể để test tải.
- [ ] Xác nhận endpoint dùng có cần cookie đăng nhập không (public endpoint thường không cần; nếu cần, chuẩn bị cookie trước).

Endpoint trending đã xác nhận sẵn từ lúc research (dùng luôn, không cần tra lại):
- `https://api.bilibili.com/x/web-interface/popular`
- `https://api.bilibili.com/x/web-interface/ranking/region?rid={rid}&day={day}`

## Việc cần làm
- [ ] Adapter `BilibiliDownloader`: `search(keyword)` → list video, `get_play_url(video_id)` → DASH streams, download + merge bằng ffmpeg.
- [ ] Adapter `BilibiliTrending`: `fetch_popular()`, `fetch_ranking(rid, day)`.
- [ ] Lưu job/video vào DB theo state machine đã thiết kế ở Phase 0.
- [ ] Dedup theo video ID trước khi tạo job tải mới.
- [ ] API + trang UI: tạo job crawl theo keyword, xem kết quả, xem trending, nút "Dùng làm từ khoá crawl" từ trang Trend.
- [ ] Batch queue qua `ProcessPoolExecutor`, giới hạn concurrency.

## Tiêu chí hoàn thành (Definition of Done)
- Nhập 1 từ khoá → tool trả về danh sách video Bilibili thật.
- Tải được ít nhất 1 video về máy, không dính watermark, phát được bằng trình phát video thông thường.
- Xem được danh sách trending Bilibili theo category đã chọn.
- Chạy lại cùng từ khoá không tải trùng video đã có.

## Ghi chú phát sinh trong lúc làm
*(để trống, cập nhật khi làm)*
