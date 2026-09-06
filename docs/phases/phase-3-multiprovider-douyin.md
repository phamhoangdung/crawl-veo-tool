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
- [ ] Cơ chế phát hiện cookie hết hạn → báo UI — đã có exception `DouyinCookieExpiredError` ở tầng adapter, chưa nối lên API/UI vì chưa có gì để test.
- [x] `app/services/cost_service.py` + `POST /api/jobs/{id}/cost-estimate` — verify bằng request thật: job free (Google/Edge-TTS) ra $0, job có cấu hình OpenAI key ra chi phí ước tính khác 0 đúng công thức.
- [x] Fallback provider khi lỗi/hết quota — đã làm ở Phase 2 (`translate_service`, `tts_service`), không cần làm lại.
- [ ] UI chọn nền tảng Bilibili/Douyin — trang Crawl hiện chưa có dropdown chọn platform (mặc định gọi thẳng Bilibili), vì Douyin chưa chạy được thật nên chưa thêm UI cho có.

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
