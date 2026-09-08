# Phase 9: Compliance & value-add cho re-up

Trạng thái: **Phần lõi xong & verify thật** (ffmpeg thật, API thật) — trừ source ledger và checklist disclosure (chưa làm, xem Ghi chú).

## Nghiên cứu quy trình thực tế (2026-09-08)

Đối chiếu tool với quy trình re-up phổ biến trên mạng ([itcenter.vn](https://itcenter.vn/2025/06/cach-kiem-tien-tu-video-trung-quoc-bilibili-tren-youtube-theo-phuong-phap-reup-chinh-chu/), [tcc-agency.com](https://tcc-agency.com/cach-reup-video-tiktok-trung-quoc/)) và chính sách YouTube hiện hành:

**Chính sách quan trọng**: 15/07 YouTube đổi tên "repetitious content" → **"inauthentic content"**, nhắm nội dung sản xuất hàng loạt/lặp lại/ít giá trị gốc. Nhưng **không đổi** chính sách reused content — clip/compilation/commentary vẫn kiếm tiền được **nếu thêm giá trị gốc thật** (biên tập kể chuyện, bình luận có phân tích, khung giáo dục). Vi phạm → tắt kiếm tiền **cả kênh**, 30 ngày sau mới xin lại được. ([vidiq](https://vidiq.com/blog/post/youtube-reused-content-policy-guide/), [creatorhandbook](https://www.creatorhandbook.net/youtube-updates-monetization-policy-for-inauthentic-content/))

Hệ quả cho tool: dịch + lồng tiếng giữ nhạc nền gốc **là transform thật**, không phải mẹo né. Nhưng chạy hàng loạt N video cùng một khuôn metadata lại đúng thứ chính sách nhắm tới → prompt sinh metadata dùng `temperature=0.7` để tránh mọi video ra cùng một giọng.

**Các mẹo "lách bản quyền" phổ biến trên mạng (tăng tốc âm thanh 105-110%, chèn tiếng chim/mưa) KHÔNG được implement** — chúng không còn tác dụng với chính sách hiện hành và không tăng giá trị thật.

Đánh giá độ phủ trước phiên này: ~65% YouTube / ~70% TikTok. Thiếu: intro/outro, watermark, nhạc nền ngoài, metadata SEO, đăng bài.

## Việc đã làm

### Media overlay (ffmpeg)
- [x] `render_timeline` nhận thêm track `"image"` — chèn logo/watermark/ảnh. Bề rộng theo **tỉ lệ khung hình** (`scale2ref`) nên co giãn đúng khi video đổi độ phân giải; x/y là **toạ độ tâm** khớp cách đặt của overlay text.
- [x] `opacity` cho watermark mờ; `start`/`end` để logo hiện theo mốc thời gian (intro branding).
- [x] **Intro/outro và nhạc nền ngoài không cần code mới** — track video nhận nhiều clip nguồn bất kỳ (có transition fade), track audio nhận file ngoài với volume riêng. Verify thật: intro 1s + video 2s + nhạc nền → đúng 3.0s, có audio stream.
- [x] Mở `image` trong `timeline_service._VALID_TRACK_TYPES` — **thiếu bước này thì logo không lưu nổi** dù renderer đã hỗ trợ (xem Ghi chú).
- [x] 4 test ffmpeg thật cho các ca trên.

### Sinh metadata SEO
- [x] `services/metadata_service.py` — sinh tiêu đề/mô tả/tag theo quy tắc từ skill `youtube-seo` (đã cài trong `.claude/skills/`): tiêu đề dưới 60 ký tự với từ khoá chính ở 5-55 ký tự đầu, 2-3 câu mở mô tả chứa từ khoá tự nhiên, tối đa 15 tag.
- [x] Bóc JSON khỏi markdown fence / lời dẫn (model hay bọc thêm), cắt về giới hạn thay vì từ chối nhưng **báo lại `title_truncated`** để không âm thầm mất chữ.
- [x] `translate_service.complete_text()` — gọi LLM với prompt tự do, **dùng chung pool key** (Phase 8) với xoay vòng khi hết quota. KHÔNG fallback Google Translate vì endpoint dịch free không nhận prompt tự do; hết key thì báo lỗi rõ.
- [x] `POST /api/videos/{id}/metadata` nhận `prompt_template` tuỳ chỉnh — **n8n truyền prompt riêng cho từng chủ đề** (ẩm thực/vlog/tin tức cần văn phong khác nhau).
- [x] `GET /api/videos/metadata/default-prompt` — lấy prompt mặc định làm điểm bắt đầu. Khai báo **sau** route có path param để không bị bắt nhầm (verify thật).
- [x] 14 test service.

### Kho asset + UI chọn file
- [x] `services/asset_service.py` — kho file dùng chung ở `storage/assets/` (logo dùng cho MỌI video nên không nằm trong thư mục của 1 video, và không bị xoá khi dọn file video đó).
- [x] Phân loại theo **công dụng** (image/video/audio) chứ không theo đuôi file, kèm giới hạn dung lượng riêng từng loại (ảnh 10 MB, audio 50 MB, video 500 MB).
- [x] Làm sạch tên file: **bỏ dấu tiếng Việt** (ffmpeg `filter_complex` xử lý đường dẫn non-ASCII không ổn định), chặn path traversal, bỏ nháy đơn/kép phá cú pháp filter. Tiền tố id để 2 file trùng tên không đè nhau.
- [x] `POST /api/assets` (upload), `POST /api/assets/import` (nhập từ đường dẫn có sẵn — bản desktop dùng đường này, không đẩy file 500 MB qua HTTP), `GET/DELETE`, `GET /{id}/file` để xem trước.
- [x] Thêm `python-multipart` vào requirements (FastAPI cần để nhận upload).
- [x] Frontend: `AssetPicker` (dialog kéo-thả + kho file, lọc theo loại) và `AssetPanel` (4 nút: intro / outro / logo / nhạc nền). Mỗi nút tự dựng clip đúng hình dạng — người dùng không phải nhớ logo là track `image` còn intro là clip đầu track `video`.
- [x] Store: `addClipToTrack` — gộp vào track cùng type+role có sẵn, track video luôn đẩy lên đầu; undo được.
- [x] 23 test asset service, 5 test validator, 5 test store, 3 test layout.

## Ghi chú
- **Lỗi đã sửa (quan trọng)**: phiên trước ghi track `image` là "xong & verify thật", nhưng thực tế chỉ verify ở tầng `ffmpeg.render_timeline`. `timeline_service._validate_operations` vẫn chỉ nhận `{video, audio, overlay}` nên **mọi timeline có logo đều bị chặn ngay khi lưu** — tính năng không dùng được qua UI lẫn API. Đã mở `image` và verify lại bằng cách đi đúng đường `save_timeline → render_timeline`.
- **Quy ước clip ảnh**: không có `start`/`end` = logo hiện suốt video (mặc định hợp lý). Có thì phải có **cả hai** — chỉ một cái thường là gõ nhầm.
- **Lỗi đã sửa**: `getClipOutputRange` trả `undefined` cho clip ảnh không mốc thời gian → bề rộng `NaN` → clip không hiện trên timeline. Nay trải suốt chiều dài video. Có test chạy đỏ khi gỡ bản vá.
- **Chưa làm**: source & rights ledger (lưu nguồn gốc video), checklist disclosure trước khi xuất. Cả hai là việc ghi chép/nhắc nhở, không chặn sản xuất.
- **Ngoài phạm vi (không đổi)**: tự động đăng lên YouTube/TikTok. Cả 2 nền tảng đều phải đăng tay.
