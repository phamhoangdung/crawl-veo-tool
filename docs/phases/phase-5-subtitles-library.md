# Phase 5: Phụ đề song ngữ + Thư viện

Trạng thái: **Xong & verify thật** (trừ cảnh báo hardsub — không có video mẫu để test, xem Ghi chú).

## Mục tiêu
Xuất phụ đề song ngữ, burn-in tuỳ chọn, có trang thư viện quản lý toàn bộ video đã xử lý.

## Phạm vi
**Trong phạm vi:** xuất `.srt`/`.vtt` gốc+dịch, burn-in bằng ffmpeg, xử lý cảnh báo hardsub có sẵn trên video gốc, template phụ đề theo tỉ lệ khung hình (9:16 vs 16:9), trang Library (danh sách, tải lẻ/tải zip hàng loạt).

**Ngoài phạm vi:** tách nhạc nền (Phase 4, độc lập).

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [ ] 1 video mẫu có hardsub sẵn — **không có**, bỏ qua tính năng cảnh báo hardsub (xem Ghi chú).
- [x] Video mẫu để test template theo tỉ lệ: **tình cờ có sẵn cả 2 tỉ lệ** từ video test đang dùng — `BV1sQZ7Y5EZa` hoá ra là 480×852 (dọc, giống Douyin dù tải từ Bilibili), đã verify nhánh dọc thật qua burn-in thật; nhánh ngang (16:9) mới verify bằng unit test (mocked), chưa có video ngang thật để chạy full burn-in.

## Việc cần làm
- [x] `app/services/subtitle_service.py`: `build_bilingual_srt()` (mỗi cue 2 dòng: gốc rồi tới dịch), `write_srt()`, `pick_font_size_for(width, height)` (video dọc dùng % cỡ chữ lớn hơn video ngang).
- [x] `app/adapters/ffmpeg.py`: thêm `get_video_dimensions()` (ffprobe), `burn_subtitles()` (filter `subtitles=...:force_style=FontSize=...`).
- [x] API: `GET /api/videos/{id}/subtitles.srt` (xuất srt), `POST /api/videos/{id}/burn-subtitles` (burn vào bản đã dub, ưu tiên `dubbed_path` nếu có, fallback `local_path`).
- [x] Trang Library (`/library`): danh sách video đã xử lý (query theo `local_path IS NOT NULL`), nút tải riêng theo variant (dubbed/burned), chọn nhiều video + tải zip (`GET /api/library/download-zip?video_ids=...&variant=...`).
- [ ] Cảnh báo hardsub — **không làm**, xem Ghi chú.
- [ ] Tuỳ chọn vị trí đặt phụ đề (trên/dưới) — chưa làm, phụ thuộc vào việc có làm hardsub detection hay không (nếu không detect hardsub thì tuỳ chọn vị trí bớt cấp thiết, mặc định burn ở dưới như chuẩn phụ đề thông thường).

## Tiêu chí hoàn thành (Definition of Done)
- [x] Xuất được file `.srt` song ngữ đúng timestamp — verify thật qua `GET /api/videos/59/subtitles.srt` (419 dòng, format đúng chuẩn SRT: index/timestamp/text).
- [x] Burn-in được phụ đề vào video test không lỗi — verify thật: `burned.mp4` tạo thành công, ffprobe xác nhận video hợp lệ (h264, 480×852, audio AAC, thời lượng khớp bản gốc). Đã test thật nhánh dọc (font-size % cao hơn); nhánh ngang mới test qua unit test logic, chưa test burn-in thật trên video ngang.
- [x] Trang Library liệt kê đúng video đã xử lý và tải về được — verify qua Playwright thật: hiển thị đúng video đã dub+burn, nút tải trỏ đúng URL backend.

## Ghi chú phát sinh trong lúc làm
- **Không làm cảnh báo hardsub**: cần OCR hoặc kiểm tra thủ công để phát hiện phụ đề cứng có sẵn trên hình, nhưng không có video mẫu nào có hardsub để test — viết detector mà không verify được có nguy cơ báo sai (false positive/negative) còn tệ hơn không có tính năng này. Để lại cho phiên sau khi có video mẫu thật.
- **Phát hiện thú vị lúc verify**: tưởng video test (`BV1sQZ7Y5EZa`, tải từ Bilibili) sẽ là 16:9 vì tài liệu research trước đó giả định Bilibili chủ yếu ngang — thực tế video này là 480×852 (dọc). Bilibili thật ra có cả nội dung dọc (video ngắn kiểu short-form), không chỉ ngang như giả định ban đầu trong plan. Nhờ vậy vô tình verify được nhánh dọc của `pick_font_size_for` bằng dữ liệu thật thay vì chỉ mock.
- Dọn 4 record video test còn sót từ Phase 1-2 (2 trong số đó là video nhạc phát hiện lúc làm Phase 2, đã dừng không xử lý tiếp) khỏi DB trước khi verify trang Library, để danh sách chỉ còn video thật sự đã xử lý hoàn chỉnh.
- Zip download dùng `zipfile` thư viện chuẩn Python, không cần thêm dependency — nén theo `ZIP_DEFLATED`, đặt tên file trong zip theo `{video_id}_{tên gốc}` để tránh trùng tên khi tải nhiều video cùng lúc.

## Editor phụ đề + sửa bug nút bước tiếp theo (phiên 2026-09-07)

**Bug: dịch xong nhưng nút "Lồng tiếng" vẫn bị khoá.** Nguyên nhân: `['video', id]` chỉ được invalidate lúc **bấm nút chạy**, không phải lúc tác vụ **xong**. Tác vụ chạy nền nên khi dịch hoàn tất, `translated_text` đã có trong DB nhưng frontend vẫn dùng cache cũ → `hasTranslation = false` → nút khoá.

Sửa trong `hooks/use-task-progress.ts`: mỗi lần SSE đẩy dữ liệu, so với lần trước để phát hiện tác vụ **vừa chuyển từ đang-chạy sang kết thúc**, rồi invalidate `['video', id]` + `['files']` + `['dashboard-stats']`. Đây là chỗ duy nhất biết được thời điểm đó.

**Editor phụ đề** (`features/videos/subtitle-editor.tsx`) — mở từ panel chi tiết, nút "Xem trước & sửa":
- **Video player** bên trái, phát bản đã xử lý nhiều nhất có sẵn (burned → dubbed → original). Phụ đề câu đang phát hiện to bên dưới để đọc khi xem.
- **Bảng sửa** bên phải: mỗi câu có 2 textarea (gốc + bản dịch), bấm mốc thời gian để nhảy tới câu đó trong video, câu đang phát được tô sáng.
- Nút Lưu chỉ bật khi có thay đổi thật (`isDirty` so từng câu), kèm nút Hoàn tác. Lưu qua `PUT /api/videos/{id}/transcript` vốn đã có sẵn.
- Panel chi tiết giờ hiện 3 câu đầu + link "Xem tất cả N câu" thay vì đổ hết danh sách.

**Endpoint mới** `GET /api/library/{id}/stream?variant=` — phát video inline trong thẻ `<video>`. Khác `/download`: **không đặt `filename`** nên trình duyệt phát thay vì tải xuống. `FileResponse` tự xử lý HTTP Range (verify: trả 206 với header `Range`) nên tua được.

**Lưu ý React**: bản nháp phụ đề reset bằng `key` trên component con, **không** dùng `useEffect` để đồng bộ state từ props — lint rule `set-state-in-effect` chặn đúng, và cách dùng `key` cũng sạch hơn.
