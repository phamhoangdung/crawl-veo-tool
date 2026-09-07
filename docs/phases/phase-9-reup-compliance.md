# Phase 9: Compliance & value-add cho re-up

Trạng thái: Chưa bắt đầu.

## Mục tiêu
Tăng "giá trị transform" thật cho video re-up (dịch + lồng tiếng đã có từ Phase 2-5) để giảm rủi ro bị tính là reused/inauthentic content theo chính sách YouTube 2026 — xem phân tích chi tiết ở [docs/scale-reup-features/plan.md](../scale-reup-features/plan.md) mục "A. Re-up video". Đây là hướng tăng giá trị nội dung thật, không phải kỹ thuật né phát hiện.

## Phạm vi
**Trong phạm vi:** source & rights ledger (lưu nguồn gốc video), title/description/tag generator theo văn phong riêng (chống lặp template giữa các video), gợi ý commentary/intro-outro do AI soạn (user duyệt/sửa trước khi dùng, không tự chèn thẳng), checklist disclosure trước khi xuất video hoàn chỉnh.

**Ngoài phạm vi:** tự động đăng lên YouTube (tool chỉ xuất file, đăng tay — không đổi trong phase này), auto-detect vi phạm bản quyền nội dung gốc (không có công cụ tool tự làm đáng tin cậy, vẫn là trách nhiệm của bạn khi chọn nguồn).

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [ ] Research yêu cầu "disclosure nội dung AI/synthetic" hiện hành của YouTube tại thời điểm implement (chính sách có thể đã đổi so với lúc research plan gốc) — quyết định còn để mở từ `docs/scale-reup-features/plan.md`.
- [ ] Quyết định: commentary/intro-outro do AI soạn full-auto hay bắt buộc user duyệt/sửa trước khi dùng? Đề xuất trong plan gốc: bắt buộc duyệt, để giữ "góc nhìn riêng" thật thay vì tự động hoá thuần tuý.
- [ ] 2-3 ví dụ title/description bạn thích (văn phong/tone kênh mong muốn) để AI generator học theo, tránh ra kết quả chung chung.

## Việc cần làm
- [ ] `app/models/video.py` hoặc bảng mới `source_ledger`: lưu tác giả gốc, ghi chú review bản quyền, trạng thái đã thêm disclosure hay chưa.
- [ ] `app/services/metadata_service.py` (mới): sinh title/description/tag qua provider AI đã chọn, dựa trên transcript + văn phong mẫu — đảm bảo prompt vary theo nội dung thật, không dùng 1 template cố định.
- [ ] `app/services/commentary_service.py` (mới): gợi ý đoạn intro/outro dựa trên transcript, trả về bản draft để user sửa qua UI, không tự chèn thẳng vào video.
- [ ] API + UI: form sửa metadata/commentary (text, không cần kéo-thả); vị trí chèn đoạn intro/outro vào video dùng chung timeline editor ở Phase 13 (kéo đặt đoạn commentary vào track chính) thay vì tự làm UI riêng; checklist disclosure (checkbox xác nhận) chặn trước khi cho tải video hoàn chỉnh.
- [ ] Test cho `metadata_service`/`commentary_service` (mock provider AI, không gọi API thật trong test).

## Tiêu chí hoàn thành (Definition of Done)
- [ ] Sinh được title/description khác nhau có ý nghĩa cho 2 video khác nhau (không giống hệt cấu trúc/câu chữ).
- [ ] Có bản draft commentary hiển thị trên UI, sửa được trước khi dùng cho video output.
- [ ] Checklist disclosure hiển thị và chặn tải file cuối cho tới khi user tick xác nhận.

## Ghi chú phát sinh trong lúc làm
(Điền khi bắt đầu code.)
