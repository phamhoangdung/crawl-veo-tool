# Phase 10: Video kể chuyện

Trạng thái: Chưa bắt đầu — phụ thuộc quyết định kịch bản (xem Nguyên liệu) và **Phase 13 (trình chỉnh sửa timeline)** cho phần sắp xếp/thay video nền + đặt caption.

**Cập nhật sau khi chốt Phase 13**: việc chọn/sắp xếp lại video nền và vị trí caption giờ làm trên timeline editor dùng chung (`frontend/src/features/editor/`) thay vì UI riêng của phase này — xem điều chỉnh trong "Việc cần làm".

## Mục tiêu
Luồng sản xuất mới: kịch bản (tự viết hoặc AI hỗ trợ) → giọng đọc TTS → ghép với video nền chọn từ thư viện, có cơ chế đa dạng hoá bắt buộc để tránh pattern lặp bị YouTube tính là inauthentic/templated content (xem phân tích rủi ro ở [docs/scale-reup-features/plan.md](../scale-reup-features/plan.md) mục "B. Video kể chuyện" — đây là hướng nội dung rủi ro chính sách cao nhất trong roadmap nếu làm sai cách).

## Phạm vi
**Trong phạm vi:** kiểu job mới không đi qua crawl, thư viện video nền (upload/tag/theo dõi tần suất dùng), module kịch bản (nhập tay + gợi ý AI), pipeline TTS → ghép video nền (tái dùng `tts_service`/`ffmpeg` adapter đã có), cảnh báo khi tổ hợp giọng+nền+cấu trúc lặp lại quá ngưỡng.

**Ngoài phạm vi:** tự sinh video nền bằng AI (dùng thư viện do bạn tự upload), caption động nâng cao kiểu TikTok (dùng chung hạ tầng ở Phase 11).

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [ ] **Phase 13 (trình chỉnh sửa timeline) đã xong** — phase này chỉ cần thêm logic chọn nền + cảnh báo lặp, dùng UI kéo-thả có sẵn.
- [ ] **Quyết định: kịch bản tự viết tay hay cần AI hỗ trợ sinh ngay từ MVP?** — câu hỏi mở từ `docs/scale-reup-features/plan.md`, cần chốt trước khi thiết kế `script_service`.
- [ ] Ít nhất 3-5 video nền mẫu (license rõ ràng — của bạn hoặc free-to-use) để test ghép và đo cảnh báo lặp.
- [ ] Xác nhận ngưỡng cảnh báo lặp tổ hợp — đề xuất mặc định trong plan gốc: cảnh báo nếu >30% trong 20 video gần nhất dùng cùng tổ hợp giọng+nền+cấu trúc. Giữ số này hay đổi?

## Việc cần làm
- [ ] `app/models/job.py`: thêm `job_type` (`crawl_reup` / `story`) hoặc tách bảng `StoryJob` riêng — quyết định lúc code dựa trên việc video kể chuyện không có `platform`/`source_url` bắt buộc như `Video` hiện tại (state machine `VideoStatus` từ `QUEUED → DOWNLOADING` không áp dụng cho luồng này, cần state machine riêng bắt đầu từ `SCRIPT_READY`).
- [ ] `app/models/background_video.py` (mới): file path, tag/category, `times_used`, `last_used_at`.
- [ ] `app/services/background_library_service.py`: upload/list/tag video nền, chọn ngẫu nhiên có trọng số ưu tiên video ít dùng.
- [ ] `app/services/script_service.py`: CRUD kịch bản, gợi ý AI (tái dùng provider adapter dịch/LLM đã có, không cần adapter mới).
- [ ] `app/services/story_pipeline_service.py`: script → TTS (tái dùng `tts_service`) → chọn nền (tái dùng `background_library_service`) → ghép (tái dùng `ffmpeg.py`) → so sánh tổ hợp giọng+nền+cấu trúc với N video gần nhất, cảnh báo nếu vượt ngưỡng đã chốt.
- [ ] Route + feature module mới `frontend/src/routes/_authenticated/story/index.tsx` + `frontend/src/features/story/index.tsx`: form nhập/chọn kịch bản + chọn/random video nền ban đầu (AI gợi ý tổ hợp), sau đó **mở timeline editor Phase 13** để sắp xếp lại đoạn nền/caption trước khi render — không tự dựng UI kéo-thả riêng; hiển thị cảnh báo lặp ngay trên màn hình chọn nền, trước khi vào editor.
- [ ] Test: `background_library_service` chọn nền có trọng số đúng (ưu tiên ít dùng); `story_pipeline_service` kích hoạt cảnh báo đúng ngưỡng đã chốt.

## Tiêu chí hoàn thành (Definition of Done)
- [ ] Tạo được 1 video kể chuyện hoàn chỉnh từ kịch bản nhập tay + video nền có sẵn — verify file output thật bằng ffprobe (audio+video hợp lệ, thời lượng khớp).
- [ ] Chạy liên tiếp nhiều lần với kịch bản/giọng gần giống nhau → hệ thống hiển thị cảnh báo lặp tổ hợp đúng như thiết kế.

## Ghi chú phát sinh trong lúc làm
(Điền khi bắt đầu code.)
