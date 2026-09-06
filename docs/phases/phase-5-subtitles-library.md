# Phase 5: Phụ đề song ngữ + Thư viện

Trạng thái: Chưa bắt đầu (phụ thuộc Phase 2, không bắt buộc chờ Phase 3/4)

## Mục tiêu
Xuất phụ đề song ngữ, burn-in tuỳ chọn, có trang thư viện quản lý toàn bộ video đã xử lý.

## Phạm vi
**Trong phạm vi:** xuất `.srt`/`.vtt` gốc+dịch, burn-in bằng ffmpeg, xử lý cảnh báo hardsub có sẵn trên video gốc, template phụ đề theo tỉ lệ khung hình (9:16 vs 16:9), trang Library (danh sách, tải lẻ/tải zip hàng loạt).

**Ngoài phạm vi:** tách nhạc nền (Phase 4, độc lập).

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [ ] 1 video mẫu có hardsub sẵn (phụ đề cứng có sẵn trên hình) để test cảnh báo/tránh chồng chữ.
- [ ] 1 video mẫu tỉ lệ 9:16 (kiểu Douyin) và 1 video 16:9 (kiểu Bilibili) để test template phụ đề khác tỉ lệ.

## Việc cần làm
- [ ] Service xuất `.srt` song ngữ từ transcript + bản dịch có timestamp.
- [ ] Service burn-in bằng ffmpeg, template vị trí/cỡ chữ theo tỉ lệ khung hình.
- [ ] Cảnh báo hardsub (kiểm tra thủ công hoặc OCR đơn giản) + tuỳ chọn vị trí đặt phụ đề mới (trên/dưới) để tránh đè lên hardsub.
- [ ] Trang Library: danh sách video đã xử lý, tải lẻ, tải zip hàng loạt.

## Tiêu chí hoàn thành (Definition of Done)
- Xuất được file `.srt` song ngữ đúng timestamp khớp video.
- Burn-in được phụ đề vào video test, không bị lỗi font/tràn khung hình ở cả 2 tỉ lệ đã test.
- Trang Library liệt kê đúng video đã xử lý và tải về được (lẻ + zip).

## Ghi chú phát sinh trong lúc làm
*(để trống, cập nhật khi làm)*
