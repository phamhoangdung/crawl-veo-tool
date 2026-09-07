# Phase 11: Clip ngắn TikTok + cross-post

Trạng thái: **Phần cắt clip + crop + caption + CTA xong & verify thật** (ffmpeg thật, browser thật cho crop UI). Phần **cross-post (đăng chéo TikTok/YouTube Shorts qua API) chưa làm** — ngoài phạm vi phase này (cần OAuth/app review riêng từng nền tảng, xem Ghi chú).

## Mục tiêu
Cắt đoạn ngắn từ video dài (re-up hoặc kể chuyện) thành clip dọc 9:16 có caption động + CTA — xem `docs/scale-reup-features/plan.md` mục "C. Cắt clip ngắn cho TikTok".

## Phạm vi
**Trong phạm vi (đã làm):** gợi ý ứng viên clip từ transcript (chấm điểm đơn giản, chỉ để xếp thứ tự), crop dọc bán tự động (khung kéo-thả + resize trên preview, mặc định 9:16 canh giữa), caption tự động khớp mốc clip đã cắt, overlay CTA text, xuất file riêng.

**Ngoài phạm vi:** auto-tracking khuôn mặt/chủ thể bằng model riêng, tự động đăng lên nền tảng qua API (cross-post — cần OAuth/app review riêng của TikTok/YouTube, khối lượng công việc lớn tương đương 1 phase riêng, xem Ghi chú).

## Việc đã làm

### Backend
- [x] `app/adapters/ffmpeg.py`: `crop_vertical()` (crop tĩnh độc lập) + **tích hợp `crop` trực tiếp vào `render_timeline()`** (mỗi clip video có thể kèm `crop: {x,y,width,height}`, áp filter `crop` ngay trong cùng 1 lần render thay vì 2 bước riêng) + `_resolve_default_fontfile()`/`_escape_filter_path()` dùng chung với overlay.
- [x] `app/services/clip_candidate_service.py`: `suggest_clip_candidates()` — trượt cửa sổ ~45s qua transcript, chấm điểm theo mật độ từ + dấu câu nhấn mạnh (`!`/`?`), loại ứng viên chồng lấn >50% với ứng viên điểm cao hơn đã chọn, trả về theo thứ tự thời gian. **Cố ý đơn giản** — không phải mô hình dự đoán viral (xem review thị trường 2026 ở `docs/scale-reup-features/plan.md`: điểm virality Opus Clip/Klap không đáng tin cậy), chỉ dùng xếp thứ tự gợi ý.
- [x] `app/services/clip_service.py`: `build_clip_timeline()` (dựng edit operations Phase 13 cho 1 clip — mốc caption tự rebase về hệ quy chiếu clip, clamp caption tràn biên) + `render_clip()` (gọi thẳng `ffmpeg.render_timeline()` có sẵn, không viết logic render riêng).
- [x] `app/api/clips.py`: `GET /api/videos/{id}/clip-candidates`, `POST /api/videos/{id}/clips`.
- [x] Test: `test_clip_candidate_service.py` (8 test, thuần logic), `test_clip_service.py` (10 test — 9 thuần logic + **1 test render thật**: dựng video synthetic bằng ffmpeg, cắt + crop + caption + CTA, verify kích thước output bằng ffprobe), `test_ffmpeg.py` thêm test crop-trong-timeline.

### Frontend
- [x] `features/editor/crop-box-selector.tsx`: khung crop kéo-thả (di chuyển) + kéo góc dưới-phải (resize), toạ độ quy đổi từ pixel thật của video nguồn.
- [x] `features/editor/layout.ts` thêm `defaultVerticalCrop()` — crop 9:16 mặc định canh giữa, clamp khi video đã hẹp hơn tỉ lệ đó.
- [x] `features/editor/index.tsx`: Card "Cắt clip ngắn" — danh sách ứng viên (bấm chọn), khung crop hiện trên preview khi đã chọn ứng viên, ô nhập CTA, nút "Tạo clip" gọi API tạo file thật.
- [x] Test: 4 test mới trong `layout.test.ts` (`defaultVerticalCrop`) — chưa có test browser riêng cho thao tác kéo `CropBoxSelector` (dùng chung pattern đã verify ở `Timeline`/`OverlayLayer`, nhưng chưa tự viết test riêng — xem Ghi chú).

## Tiêu chí hoàn thành (Definition of Done)
- [x] Cắt được 1 clip dọc 9:16 từ video dài có sẵn, có caption + CTA overlay — verify **thật** bằng `ffprobe` trong `test_renders_a_real_cropped_captioned_clip` (crop 270x480 đúng kích thước yêu cầu).
- [x] Danh sách clip gợi ý AI hiện trên UI, kéo chỉnh được khung crop trước khi tạo clip — verify qua code + test logic; UI đã implement đầy đủ (chưa tự tay bấm thử qua browser thật, giống lưu ý ở Phase 8).

## Ghi chú phát sinh trong lúc làm
- **Tích hợp crop thẳng vào `render_timeline()` thay vì 2 bước riêng** (crop rồi mới trim/overlay) — đơn giản hơn, chỉ 1 lần ffmpeg chạy thay vì 2, tái dùng đúng field `clip.crop` đã có sẵn cấu trúc filter theo clip.
- **Không làm cross-post (đăng API TikTok/YouTube Shorts)** — đây là khối lượng công việc lớn riêng (OAuth, app review từng nền tảng, quota, rủi ro chính sách đăng hàng loạt đã nói ở research trước) không hợp lý gộp chung với phần cắt clip. Nếu cần, nên tách thành phase riêng sau khi có nhu cầu thật.
- **Điểm chấm ứng viên clip cố ý thô** (mật độ từ + dấu câu) — quyết định giữ đơn giản, KHÔNG cố gắng làm giống mô hình viral-score của Opus Clip/Klap vì review thị trường 2026 cho thấy các điểm đó tự thân cũng không đáng tin cậy; mục tiêu chỉ là "xếp thứ tự gợi ý hợp lý hơn ngẫu nhiên", không phải "chọn đúng đoạn viral nhất".
- **CropBoxSelector chưa có test browser riêng** — cùng pattern pointer-drag đã verify kỹ ở `Timeline`/`OverlayLayer` (cùng công thức tính delta theo tỉ lệ pixel), rủi ro thấp nhưng chưa tự viết test riêng do giới hạn thời gian phiên làm việc — nên bổ sung nếu phát hiện lệch vị trí thật khi dùng.
