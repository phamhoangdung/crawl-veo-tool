# Phase 6: Hardening & Ops

Trạng thái: **Phần cốt lõi xong & verify thật** (storage cleanup, health-check, setup docs). Celery/Redis: quyết định KHÔNG cần — xem Ghi chú.

## Mục tiêu
Ổn định hoá tool cho vận hành lâu dài ở quy mô cá nhân (chưa phải multi-tenant/bán — đó là [phase-7-productization.md](phase-7-productization.md), tương lai).

## Phạm vi
**Trong phạm vi:** đánh giá nâng cấp Celery/Redis nếu `ProcessPoolExecutor` không đủ, storage cleanup/retention, unit test cho adapter, health-check định kỳ cho downloader, packaging môi trường Windows.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [x] Số liệu thực tế về concurrency: **chưa từng có job đồng thời thật nào** qua Phase 1-5 — mọi request xử lý tuần tự trong 1 request HTTP, `ProcessPoolExecutor` (đã dự tính từ Phase 0) chưa từng được implement vì chưa cần. Kết luận: chưa cần Celery/Redis (xem Ghi chú).
- [x] Đã đọc lại "Ghi chú phát sinh" các phase 0-5 để biết ưu tiên hardening: lỗi hay gặp nhất là (1) tiến trình `uvicorn --reload` không thay hẳn worker khi code đổi, (2) DB schema không tự migrate khi thêm cột mới, (3) PATH ffmpeg không refresh trong terminal đang mở.

## Việc cần làm
- [x] `app/services/storage_cleanup_service.py`: `cleanup_old_job_folders(max_age_days)` xoá thư mục job cũ (theo mtime), `get_storage_usage_bytes()` — chưa nối lên API/cron, xem Ghi chú.
- [x] Test cho adapter/service đã có coverage đầy đủ: `bilibili/client.py` (5 test), `cost_service` (2), `dubbing_service` time-stretch logic (3), `subtitle_service` (3), `storage_cleanup_service` (2) — tổng 15 test, tất cả mock/không gọi mạng thật.
- [x] `app/services/health_check_service.py` + `GET /health/downloader` — gọi thật 3 endpoint Bilibili (popular/ranking/search), verify bằng request thật. **Bắt được 1 lỗi thật ngay khi viết**: dùng nhầm `day=1` (giá trị không hợp lệ cho endpoint ranking) — sửa thành `day=3`, xác nhận lại `healthy: true`. Douyin không có health-check vì adapter chưa verify được (Phase 3).
- [x] `SETUP.md` — hướng dẫn cài đặt Windows đầy đủ, viết dựa trên các vướng mắc **thật đã gặp** trong suốt quá trình build (không phải đoán trước): lỗi PATH ffmpeg, lỗi WinError 10013, lỗi thiếu cột DB.
- [ ] Nối `cleanup_old_job_folders` lên 1 endpoint/cron thật — code đã có, chưa có nơi gọi định kỳ (không có scheduler trong dự án, cần quyết định dùng gì — cron ngoài gọi 1 endpoint, hay APScheduler trong app — để phiên sau).

## Tiêu chí hoàn thành (Definition of Done)
- [~] Tool chạy ổn định qua nhiều batch lớn liên tục — chưa test thật với batch lớn (nhiều job/video cùng lúc), vì chưa có nhu cầu thật để tạo tình huống đó. Storage cleanup đã sẵn sàng nhưng chưa được gọi tự động.
- [x] Có test tự động chạy pass cho các adapter chính — 15/15 test pass, verify thật (không chỉ báo cáo).
- [x] Có tài liệu cài đặt đủ để tự cài lại từ đầu — `SETUP.md`, dựa trên kinh nghiệm thật.

## Ghi chú phát sinh trong lúc làm
- **Quyết định không làm Celery/Redis**: toàn bộ dự án tới giờ chạy đồng bộ trong request HTTP (không có `ProcessPoolExecutor` thật, dù Phase 0 dự tính dùng nó). Việc này hoạt động ổn cho quy mô cá nhân xử lý 1 video tại 1 thời điểm (đúng use case thật đã test). Thêm Celery/Redis lúc này là over-engineering không có bằng chứng cần thiết — đúng tinh thần "không thêm abstraction chưa cần" trong `docs/conventions.md`. Nên làm khi thực sự có nhu cầu chạy nhiều video song song.
- **Health-check tự bắt lỗi ngay trong lúc viết nó** (dùng sai giá trị `day` cho ranking endpoint) — minh chứng cho giá trị thật của tính năng này: không chỉ để phát hiện Bilibili đổi API, mà còn bắt được lỗi code của chính mình trước khi thành bug âm thầm.
- Storage cleanup viết xong nhưng chưa nối lên chỗ nào gọi định kỳ — dự án chưa có concept "scheduler/cron job" nội bộ, cần quyết định hướng (cron hệ điều hành gọi 1 endpoint, hay thêm APScheduler chạy trong process) trước khi làm tiếp, không tự chọn thay vì để đó không dùng được.
