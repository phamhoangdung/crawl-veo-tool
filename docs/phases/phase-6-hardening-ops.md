# Phase 6: Hardening & Ops

Trạng thái: Chưa bắt đầu (phụ thuộc các phase trước đã chạy thật để biết giới hạn thực tế)

## Mục tiêu
Ổn định hoá tool cho vận hành lâu dài ở quy mô cá nhân (chưa phải multi-tenant/bán — đó là [phase-7-productization.md](phase-7-productization.md), tương lai).

## Phạm vi
**Trong phạm vi:** đánh giá nâng cấp Celery/Redis nếu `ProcessPoolExecutor` không đủ, storage cleanup/retention, unit test cho adapter, health-check định kỳ cho downloader, packaging môi trường Windows.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [ ] Số liệu thực tế về số job đồng thời đã gặp ở các phase trước (để quyết định có thật sự cần Celery/Redis hay `ProcessPoolExecutor` vẫn đủ).
- [ ] Danh sách lỗi/vướng mắc đã ghi nhận ở "Ghi chú phát sinh" của các phase 0-5 (đọc lại để biết ưu tiên hardening chỗ nào).

## Việc cần làm
- [ ] (Nếu cần) Setup Celery + Redis thay `ProcessPoolExecutor`.
- [ ] Retention policy storage (tự xoá file trung gian sau X ngày, hoặc giới hạn tổng dung lượng job).
- [ ] Unit test cho từng adapter provider (download, translate, tts).
- [ ] Health-check định kỳ cho Bilibili/Douyin downloader (phát hiện sớm khi nền tảng đổi API).
- [ ] Viết hướng dẫn cài đặt đầy đủ trên Windows (`requirements.txt`/lockfile, cài ffmpeg, driver CUDA nếu dùng GPU).

## Tiêu chí hoàn thành (Definition of Done)
- Tool chạy ổn định qua nhiều batch lớn liên tục mà không tràn ổ đĩa.
- Có test tự động chạy pass cho các adapter chính.
- Có tài liệu cài đặt đủ để tự cài lại từ đầu trên máy khác.

## Ghi chú phát sinh trong lúc làm
*(để trống, cập nhật khi làm)*
