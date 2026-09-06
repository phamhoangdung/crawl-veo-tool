# Phase 4: Audio Quality (tách nhạc nền) + Video dài

Trạng thái: Chưa bắt đầu (phụ thuộc Phase 2, không bắt buộc chờ Phase 3)

## Mục tiêu
Giữ nhạc nền/hiệu ứng gốc khi lồng tiếng thay vì thay toàn bộ track âm thanh; xử lý được video dài mà không tràn RAM/timeout.

## Phạm vi
**Trong phạm vi:** Demucs tách vocal/nhạc nền, mix giọng mới với nhạc nền đã tách, time-stretch khớp thời lượng câu, chunk video dài theo khoảng lặng trước khi transcribe/tách nhạc.

**Ngoài phạm vi:** phụ đề, thư viện quản lý video.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [ ] Cài `demucs`, xác nhận chạy được (CPU trước, GPU nếu có).
- [ ] 1 video mẫu dài (>10 phút) để test chunk theo khoảng lặng.
- [ ] Chọn cách time-stretch cụ thể: `pyrubberband` (chất lượng tốt hơn, cần cài rubberband binary) hay ffmpeg filter `atempo` (đơn giản hơn, cài sẵn cùng ffmpeg) — chốt hướng khi vào phase, không để mặc định.

## Việc cần làm
- [ ] Service tách audio bằng Demucs, lưu 2 track (vocal, nhạc nền) theo cấu trúc thư mục multi-track đã thiết kế từ Phase 0.
- [ ] Service mix giọng mới + nhạc nền, canh time-stretch theo timestamp gốc.
- [ ] Silence-based chunking cho video dài trước khi transcribe/Demucs.
- [ ] UI: tuỳ chọn bật/tắt giữ nhạc nền theo từng job.

## Tiêu chí hoàn thành (Definition of Done)
- Video lồng tiếng ra vẫn nghe được nhạc nền/hiệu ứng gốc (không bị câm hoàn toàn phần nhạc).
- Xử lý được video dài (>10 phút) không lỗi tràn RAM/timeout.
- Giọng đọc mới khớp thời lượng với đoạn gốc trong sai số chấp nhận được (không bị lệch quá xa, nghe tự nhiên).

## Ghi chú phát sinh trong lúc làm
*(để trống, cập nhật khi làm)*
