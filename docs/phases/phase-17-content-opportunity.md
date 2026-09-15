# Phase 17: Xu hướng YouTube + Chủ đề cơ hội

Trạng thái: **Phần lõi xong** — code viết đầy đủ, test mock pass (415 test backend), verify UI thật qua Playwright (không lỗi console). **Chưa verify được gọi API YouTube thật** — cần bạn cung cấp 1 API key YouTube Data API v3.

## Bối cảnh

Người dùng làm rõ mục tiêu sản phẩm: crawl video Trung Quốc → dịch/lồng tiếng → đăng YouTube/TikTok kiếm tiền ("video ăn liền"). Dashboard cũ chỉ có 4 số liệu tiến độ pipeline, không giúp quyết định "nên làm chủ đề gì tiếp theo". Yêu cầu: (1) xem xu hướng YouTube/TikTok, (2) trang cấu hình "chủ đề quan tâm" + độ dễ khai thác.

**Quyết định đã chốt qua research + hỏi người dùng (2026-09-16):**
- **YouTube trước, TikTok để sau.** YouTube Data API v3 chính thức, miễn phí (quota 10.000 unit/ngày), tài liệu công khai đầy đủ. TikTok không có API trending công khai miễn phí — Creative Center là trang JS nặng cần scrape (rủi ro giống Douyin, hiện đang tạm dừng), hoặc API trả phí (Apify/ScrapeCreators). Khớp với quyết định Phase 9/11 đã hoãn đăng TikTok tự động.
- **Người dùng xác nhận rõ: "ytb chỉ là để xem xu hướng thôi, chứ ko lấy video về"** — khác Bilibili/Douyin, YouTube trong tool này KHÔNG có chức năng tải video, chỉ xem để lấy ý tưởng.
- **Điểm "cơ hội khai thác" tính tự động bằng dữ liệu YouTube thật** (không chỉ ghi chú thủ công) — người dùng chọn phương án này khi được hỏi.

## Mục tiêu
Thêm khả năng xem xu hướng YouTube (chỉ xem) + trang quản lý chủ đề nội dung có tính điểm "dễ khai thác" tự động, dùng để quyết định nên tìm nguồn Trung Quốc nào trên Bilibili để dịch tiếp theo.

## Phạm vi
**Trong phạm vi:** adapter YouTube Data API v3 (categories/mostPopular/search/channels), tab "YouTube" trong trang Trending (xem — không tải), trang "Chủ đề quan tâm" (CRUD + tính điểm), provider "youtube" trong pool API key.

**Ngoài phạm vi:** TikTok (mọi hình thức — xem lẫn tải), tải/đăng video lên YouTube, Dashboard redesign (chưa làm — xem "Việc chưa làm").

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [ ] **1 API key YouTube Data API v3** — chưa có, đây là thứ duy nhất chặn lại. Lấy tại [console.cloud.google.com](https://console.cloud.google.com/apis/credentials): tạo project (hoặc dùng project có sẵn) → Enable API "YouTube Data API v3" → Credentials → Create API key. Miễn phí, không cần thẻ tín dụng cho quota mặc định. Dán vào trang API Keys của tool, provider "YouTube Data API".
- [x] Quyết định hướng TikTok: **hoãn** (xem "Bối cảnh").
- [x] Quyết định mức tự động hoá điểm chủ đề: **tự tính bằng API thật**.

## Việc cần làm
- [x] `app/adapters/youtube/client.py` — `YouTubeClient`: `list_video_categories`, `list_most_popular` (chart=mostPopular), `search_videos`, `list_videos_stats`, `list_channels_stats`. Ánh xạ lỗi Google (`quotaExceeded`→`YouTubeQuotaExceededError`, `keyInvalid`/`badRequest`→`YouTubeInvalidKeyError`) dựa theo tài liệu chính thức developers.google.com/youtube/v3 — khác Bilibili/Douyin, không cần đoán field.
- [x] `app/models/topic.py` — bảng `topics` (name, query, note, score, sample_video_count, competition_count, top_video_title/url, scored_at). Không lưu lịch sử theo thời gian như `CategorySnapshot` — chỉ giữ lần tính gần nhất.
- [x] `app/services/youtube_service.py` — dùng chung pool API key (Phase 8: `pick_decrypted_key`/`mark_key_result`) để có rotation/failover nếu sau này thêm nhiều key.
- [x] `app/services/topic_service.py` — thuật toán tính điểm: search 25 video view cao nhất 30 ngày qua theo từ khoá (100 unit) → lấy view thật + số sub kênh đăng (2 unit) → điểm = TRUNG VỊ tỉ lệ view/sub. Cooldown 10 phút/topic chống bấm nhầm tốn quota.
- [x] API: `GET/POST /api/topics`, `DELETE /api/topics/{id}`, `POST /api/topics/{id}/score`; `GET /api/trending/youtube/{status,categories,trending}`.
- [x] Frontend: tab "YouTube" trong Trending (platform switcher Bilibili/YouTube) — category tabs + lưới video CHỈ XEM (popup nhúng player YouTube hoặc mở trên YouTube, không checkbox/tải). Trang mới `/topics` "Chủ đề quan tâm" (form thêm chủ đề + card hiện điểm cơ hội với nhãn định tính Cao/Trung bình/Thấp). Thêm "YouTube Data API" vào danh sách provider ở trang API Keys. Thêm mục "Chủ đề quan tâm" vào sidebar (nhóm "Nội dung", cạnh "Xu hướng").
- [x] 17 test mới (`test_youtube_client.py` 7 test mock `httpx.MockTransport`, `test_topic_service.py` 10 test mock `run_with_key`) — không gọi API thật.
- [x] Verify UI thật qua Playwright: sidebar link, trang Topics thêm/hiện chủ đề, tab YouTube trong Trending hiện đúng cảnh báo "chưa cấu hình", API Keys có provider mới. Không lỗi console.
- [ ] **Chưa verify**: gọi API YouTube thật (categories/mostPopular/search/channels) — cần key thật từ bạn.

## Việc chưa làm (ngoài phạm vi phiên này)
- **Dashboard redesign** — người dùng có nhắc tới nhưng phiên này ưu tiên làm xong hạ tầng YouTube + trang Topics trước. Khi có key thật để verify xong, nên quay lại thêm 1 widget "Chủ đề nổi bật"/"Video YouTube đang hot trong chủ đề bạn theo dõi" vào Dashboard, tái dùng dữ liệu đã có ở đây.
- **TikTok** — xem "Bối cảnh", hoãn có chủ đích.
- Điểm chủ đề hiện chỉ dựa 1 tín hiệu (tỉ lệ view/sub). Có thể tinh chỉnh thêm sau khi thấy điểm thật có phản ánh đúng trực giác không (vd cộng thêm trọng số theo độ mới của video, hoặc trừ điểm nếu top video toàn từ 1-2 kênh lớn).

## Tiêu chí hoàn thành (Definition of Done)
- [x] Xem được danh sách chuyên mục + video đang hot của YouTube ngay trong trang Trending, không cần rời tool — code xong, verify UI (chưa verify dữ liệu thật vì thiếu key).
- [x] Có nơi lưu & quản lý danh sách chủ đề quan tâm, xoá được — verify UI thật (thêm/xoá chủ đề qua Playwright).
- [ ] Điểm "dễ khai thác" phản ánh đúng dữ liệu YouTube thật — thuật toán viết xong + test logic (trung vị tỉ lệ view/sub từ dữ liệu giả lập đúng), nhưng chưa chạy với dữ liệu YouTube thật để xác nhận con số có ý nghĩa trong thực tế.

## Ghi chú phát sinh

### Nghiên cứu dùng skill (2026-09-16)
Dùng `find-skills` tìm skill nghiên cứu xu hướng YouTube/TikTok trước khi tự viết. Kết quả: các skill liên quan (`apidojo-io/apidojo-skills`, `scrapecreators/social-media-research-skills`) đều bọc quanh API trả phí (Apify token, ScrapeCreators) — không có skill "miễn phí, chỉ hướng dẫn phương pháp". Quyết định tự viết adapter thẳng vào YouTube Data API v3 chính thức (miễn phí thật) thay vì cài skill nào — khớp với việc dự án luôn ưu tiên nguồn chính thức/miễn phí khi có, chỉ cân nhắc trả phí khi không còn lựa chọn khác (giống lý do từng cân nhắc Apify/ScrapeCreators cho TikTok).

### Field mapping YouTube — verify qua tài liệu chính thức, không đoán
`videos.list` (mostPopular) trả `id` là string trực tiếp; `search.list` trả `id.videoId` (object). Nhầm 2 dạng này là lỗi hay gặp khi tích hợp API này (ghi chú lại để phiên sau không đoán nhầm). `search.list` KHÔNG trả `statistics` — phải gọi thêm `videos.list` theo id để lấy view/like thật, đây là lý do `compute_score()` cần 3 lệnh gọi API (search → videos → channels) thay vì 1.

### Vì sao không dùng lịch sử điểm theo thời gian như Bilibili category
Bilibili `CategorySnapshot` tích luỹ điểm theo thời gian để vẽ đường xu hướng (mục đích: xem 1 chuyên mục Bilibili đang lên/xuống). Topic ở đây mục đích khác — quyết định "có nên khai thác chủ đề X hay không" tại thời điểm xem, nên chỉ cần điểm mới nhất. Nếu sau này muốn xem điểm chủ đề thay đổi ra sao theo thời gian, thêm bảng snapshot tương tự sau, không cần làm ngay.

### Việc tiếp theo khi có API key YouTube thật
1. Dán key vào trang API Keys, provider "YouTube Data API".
2. Mở Trending → tab YouTube → xem chuyên mục + video có tải đúng dữ liệu thật không.
3. Mở trang Chủ đề quan tâm → thêm 1-2 chủ đề thật → bấm "Tính điểm cơ hội" → xem điểm/video tiêu biểu có hợp lý không (so với trực giác của bạn về chủ đề đó).
4. Nếu điểm ra con số vô lý (vd toàn 0, hoặc quá cao bất thường) — khả năng cao là field mapping sai ở bước nào đó (search/videos/channels response thật khác tài liệu), cần dán response thật vào để soi lại, không đoán tiếp.
5. Sau khi verify xong, quay lại làm Dashboard widget (xem "Việc chưa làm").
