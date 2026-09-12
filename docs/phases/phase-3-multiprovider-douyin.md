# Phase 3: Multi-provider + Douyin

Trạng thái: **Một phần** — cost estimation đã xong & verify được; Douyin adapter viết theo cơ chế công khai nhưng **chưa test được** (cần cookie Douyin thật của bạn, xem Ghi chú).

## Mục tiêu
Thêm nền tảng Douyin, thêm các provider AI khác, thêm kiểm soát chi phí trước khi chạy batch lớn.

## Phạm vi
**Trong phạm vi:** `DouyinDownloader` (dựa Evil0ctal lib, xử lý cookie + tự phát hiện cookie hết hạn), thêm adapter provider dịch/TTS thứ 2-3 với capability flags, dry-run cost estimate + budget cap trước khi submit batch, fallback provider khi lỗi/hết quota.

**Ngoài phạm vi:** tách nhạc nền, phụ đề, video dài.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [ ] **Cookie Douyin hợp lệ** — chưa có, cần bạn đăng nhập Douyin trên trình duyệt rồi lấy cookie qua devtools. Đây là thứ duy nhất tôi không tự làm được (cần tài khoản cá nhân của bạn).
- [x] Provider dịch/TTS bổ sung: **không thêm provider mới** — quyết định giữ nguyên cặp OpenAI/Google (dịch) và ElevenLabs/Edge-TTS (giọng) từ Phase 2, đã đủ "2 provider khác nhau" theo DoD, tránh thêm provider chưa có key thật để test.
- [ ] Pin version/fork [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) — chưa làm, xem Ghi chú (đổi hướng tự viết adapter riêng gọn hơn thay vì kéo nguyên thư viện lớn).
- [ ] 1 URL video Douyin mẫu để test tải — chưa có.

## Việc cần làm
- [x] `app/adapters/douyin/client.py`: `resolve_share_url()` (theo redirect link share ra aweme_id), `get_video_detail()` (gọi endpoint detail lấy metadata + play_addr), `DouyinCookieExpiredError` khi gặp 401/403 — **viết theo cơ chế công khai, chưa chạy được với dữ liệu thật** vì thiếu cookie + URL mẫu.
- [x] Cơ chế phát hiện cookie hết hạn → báo UI — **đã nối lên API/UI** (409 riêng, khác 400 của "chưa có cookie"), test bằng mock. Chưa gặp cookie hết hạn thật.
- [x] `app/services/cost_service.py` + `POST /api/jobs/{id}/cost-estimate` — verify bằng request thật: job free (Google/Edge-TTS) ra $0, job có cấu hình OpenAI key ra chi phí ước tính khác 0 đúng công thức.
- [x] Fallback provider khi lỗi/hết quota — đã làm ở Phase 2 (`translate_service`, `tts_service`), không cần làm lại.
- [x] UI chọn nền tảng Bilibili/Douyin — **đã có** (2 nút ở thẻ "Tạo job crawl"). Chọn Douyin hiện panel riêng nói rõ mức hỗ trợ hiện tại, không giả vờ như Bilibili.

## Tiêu chí hoàn thành (Definition of Done)
- [ ] Crawl + tải được video Douyin không watermark — **bị chặn, cần cookie + URL mẫu thật từ bạn**.
- [x] Chạy pipeline với ít nhất 2 provider khác nhau cho cùng 1 tác vụ — đã có từ Phase 2 (OpenAI/Google, ElevenLabs/Edge-TTS), tự đổi qua lại theo key đã cấu hình (không phải chọn tay qua UI, nhưng đáp ứng đúng ý ban đầu "ưu tiên key trả phí nếu hoạt động").
- [x] Thấy cảnh báo ước tính chi phí trước khi chạy batch — verify qua `POST /api/jobs/{id}/cost-estimate`, có field `warning` khi chi phí ước tính vượt ngưỡng $1.
- [ ] Cookie Douyin hết hạn được phát hiện và báo rõ ràng — code đã có (`DouyinCookieExpiredError`), chưa verify được vì chưa có cookie thật để tạo tình huống hết hạn.

## Ghi chú phát sinh trong lúc làm
- **Douyin là phần duy nhất trong toàn bộ dự án cần thông tin cá nhân của bạn (cookie đăng nhập) mà tôi không tự lấy được** — khác với Bilibili, nơi mọi thứ (search/trending/download) đều test được bằng request công khai không cần tài khoản. Đây là lý do Phase 3 chỉ xong một phần khi làm tự động.
- Việc cần làm khi bạn có cookie + 1 URL Douyin mẫu: (1) dán cookie vào `DouyinClient(cookie=...)`, (2) thử `resolve_share_url()` với URL share thật, (3) kiểm tra `get_video_detail()` trả về đúng `play_addr` không watermark, (4) nếu endpoint `iesdouyin.com/aweme/v1/web/aweme/detail/` bị chặn/đổi response (Douyin đổi API khá thường xuyên), cần dò lại endpoint đúng tại thời điểm đó — nên bắt đầu bằng cách so sánh với cách [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) đang làm nếu endpoint viết sẵn không còn hoạt động.
- Đổi hướng khỏi việc pin/fork nguyên thư viện Evil0ctal: thư viện đó khá lớn (hỗ trợ nhiều nền tảng, nhiều tính năng không cần), viết adapter riêng gọn theo đúng nhu cầu (chỉ cần resolve share link + lấy play_addr) dễ bảo trì hơn khi Douyin đổi API — chỉ cần sửa 1 file nhỏ thay vì theo dõi cập nhật của 1 dependency ngoài.
- Cost estimate hiện tính theo **ước tính thô** (số giây video × ~3 ký tự/giây × giá provider) — không chính xác so với hoá đơn thật (giá thực tế theo token/ký tự cụ thể của từng nhà cung cấp, có thể có tier/discount). Đủ dùng để cảnh báo "coi chừng chi phí" trước khi chạy batch lớn, không nên dùng để tính tiền chính xác.


### Phiên 2026-09-12 — làm phần chắc chắn đúng, không đoán phần còn lại

**Ranh giới đã chốt:** làm cấu hình cookie + phân loại lỗi + UI; **cố ý KHÔNG viết**
phần bóc tách link không watermark. Lý do: API detail của Douyin không có tài liệu
công khai, hình dạng JSON chỉ biết được khi gọi thật bằng cookie hợp lệ. Code bóc
tách viết theo phỏng đoán sẽ trông như chạy được nhưng sai ở chỗ **không ai kiểm ra
được** cho tới lúc thử thật — tệ hơn là không có gì.

**Đã làm:**
- `DOUYIN_COOKIE` trong settings; khoảng trắng cũng tính là chưa cấu hình (dán nhầm
  vào `.env` mà vẫn gửi header `Cookie` rỗng sẽ nhận lỗi khó hiểu từ Douyin).
- `app/services/douyin_service.py`: `is_configured()` + `probe_share_url()`.
- Phân biệt **hai lỗi khác nhau**, vì việc người dùng phải làm cũng khác nhau:
  - chưa có cookie → **400**, kèm hướng dẫn lấy cookie ở đâu;
  - cookie hết hạn (`DouyinCookieExpiredError`) → **409**, "cookie cũ hết hạn, lấy lại".
  Gộp chung thì UI không hướng dẫn đúng được.
- Endpoint `GET /api/jobs/douyin/status` + `POST /api/jobs/douyin/probe`.
- UI: 2 nút chọn nền tảng ở trang Crawl. Chọn Douyin hiện panel riêng (ô dán link
  chia sẻ) thay vì ô tìm từ khoá — hai nền tảng khác hẳn nhau về cách tìm, ép chung
  một ô input sẽ gây hiểu nhầm. Panel nói thẳng "chưa tải được video".

**`probe_share_url()` không phải làm cho có.** Nó gọi đúng 2 bước đã có (resolve link
ngắn → lấy detail) rồi **in ra các trường JSON nhận được**. Khi bạn có cookie thật,
chạy một lần là biết chính xác cần đọc trường nào để lấy link không watermark — tức là
nó biến phần "không kiểm chứng được" thành kiểm chứng được. Đã xử lý cả 2 hình dạng
Douyin từng dùng (`aweme_detail` và `aweme_list[0]`), gặp dạng lạ thì trả rỗng chứ
không crash.

**8 test tự động** cho phần kiểm chứng được (phân loại cấu hình, 2 loại lỗi, 3 hình
dạng JSON). **Chưa chạy lần nào với cookie thật** — vẫn cần bạn cung cấp.

**Việc tiếp theo khi có cookie:** chạy "Thăm dò" trên UI với 1 link Douyin, đưa danh
sách trường mà nó in ra vào phiên sau → viết `download_douyin_video()` có căn cứ.
