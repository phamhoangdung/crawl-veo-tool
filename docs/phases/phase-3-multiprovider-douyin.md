# Phase 3: Multi-provider + Douyin

Trạng thái: Chưa bắt đầu (phụ thuộc Phase 2)

## Mục tiêu
Thêm nền tảng Douyin, thêm các provider AI khác, thêm kiểm soát chi phí trước khi chạy batch lớn.

## Phạm vi
**Trong phạm vi:** `DouyinDownloader` (dựa Evil0ctal lib, xử lý cookie + tự phát hiện cookie hết hạn), thêm adapter provider dịch/TTS thứ 2-3 với capability flags, dry-run cost estimate + budget cap trước khi submit batch, fallback provider khi lỗi/hết quota.

**Ngoài phạm vi:** tách nhạc nền, phụ đề, video dài.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [ ] Cookie Douyin hợp lệ (đăng nhập tài khoản Douyin trên trình duyệt, lấy cookie qua devtools).
- [ ] API key cho provider bổ sung muốn thêm (Google Translate/Cloud TTS, Azure Speech, DeepL... — chọn theo nhu cầu thực tế lúc này).
- [ ] Pin version hoặc fork riêng [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) thay vì phụ thuộc trực tiếp upstream.
- [ ] 1 URL video Douyin mẫu để test tải.

## Việc cần làm
- [ ] Adapter `DouyinDownloader`: search, no-watermark download (lấy `play_addr` gốc qua endpoint mobile/web API).
- [ ] Cơ chế phát hiện cookie hết hạn (lỗi 401/403 lặp lại) → báo UI yêu cầu refresh thay vì fail âm thầm.
- [ ] Thêm 1-2 adapter provider dịch/TTS mới, gắn capability flags (giới hạn ký tự/request, ngôn ngữ hỗ trợ, streaming vs batch).
- [ ] Cơ chế fallback provider khi lỗi/hết quota.
- [ ] Dry-run cost estimate trước khi submit batch + budget cap theo job.
- [ ] UI chọn nền tảng (Bilibili/Douyin) + chọn provider theo từng tác vụ.

## Tiêu chí hoàn thành (Definition of Done)
- Crawl + tải được video Douyin không watermark.
- Chạy pipeline với ít nhất 2 provider khác nhau cho cùng 1 tác vụ (đổi qua lại được từ UI).
- Thấy cảnh báo ước tính chi phí trước khi chạy 1 batch lớn (vd >20 video).
- Cookie Douyin hết hạn được phát hiện và báo rõ ràng thay vì job fail không lý do.

## Ghi chú phát sinh trong lúc làm
*(để trống, cập nhật khi làm)*
