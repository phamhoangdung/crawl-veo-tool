# Phase 3: Multi-provider + Douyin

Trạng thái: **Một phần** — cost estimation xong & verify được. Tải video: giao cho yt-dlp, viết xong + test mock, **chưa chạy thật** (cần 1 cookie ẩn danh + URL mẫu). Tìm kiếm từ khoá: hạ tầng ký `a_bogus` xong & verify request thật, nhưng **bạn không có tài khoản Douyin** — mà tìm kiếm bắt buộc cookie đăng nhập tài khoản thật (chặn cứng phía Douyin, không né được). **Đã quyết định (2026-09-15 chiều): tạm dừng phần tìm kiếm ở đây**, không đầu tư thêm cho tới khi có tài khoản hoặc đổi hướng — xem Ghi chú.

## Mục tiêu
Thêm nền tảng Douyin, thêm các provider AI khác, thêm kiểm soát chi phí trước khi chạy batch lớn.

## Phạm vi
**Trong phạm vi:** `DouyinDownloader` (dựa Evil0ctal lib, xử lý cookie + tự phát hiện cookie hết hạn), thêm adapter provider dịch/TTS thứ 2-3 với capability flags, dry-run cost estimate + budget cap trước khi submit batch, fallback provider khi lỗi/hết quota.

**Ngoài phạm vi:** tách nhạc nền, phụ đề, video dài.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [ ] **1 cookie Douyin ẩn danh** (đủ cho tải video) — chưa có. Chỉ cần mở trình duyệt vào douyin.com một lần (JS challenge tự sinh cookie ẩn danh `s_v_web_id`), rồi lấy cookie qua DevTools → Network → copy header `Cookie`. KHÔNG cần đăng nhập tài khoản cho việc này.
- [ ] **1 cookie Douyin ĐĂNG NHẬP tài khoản thật** (bắt buộc riêng cho tìm kiếm từ khoá) — **BLOCKED: bạn hiện không có tài khoản Douyin**. Đã hỏi 3 hướng xử lý (tạo tài khoản mới miễn phí / bỏ tìm kiếm chỉ dùng "dán link" / tạm dừng quyết định) — bạn chọn **tạm dừng, quyết định sau**. Không chờ đợi thụ động ở mục này, chỉ mở lại khi bạn chủ động quay lại.
- [x] Provider dịch/TTS bổ sung: **không thêm provider mới** — quyết định giữ nguyên cặp OpenAI/Google (dịch) và ElevenLabs/Edge-TTS (giọng) từ Phase 2, đã đủ "2 provider khác nhau" theo DoD, tránh thêm provider chưa có key thật để test.
- [x] Pin version/fork Evil0ctal — **đổi hướng dùng yt-dlp** cho tải video (xem Ghi chú 2026-09-15 sáng); phần tìm kiếm thì **vendor thuật toán ký `a_bogus` từ [f2](https://github.com/Johnserf-Seed/f2)** thay vì Evil0ctal (xem Ghi chú 2026-09-15 chiều).
- [ ] 1 URL/link share video Douyin mẫu để test tải — chưa có.
- [ ] 1 từ khoá mẫu để test tìm kiếm sau khi có cookie đăng nhập — chưa có.

## Việc cần làm
- [x] `app/adapters/douyin/client.py`: `resolve_share_url()` (theo redirect link share ra aweme_id), `get_video_detail()` (gọi endpoint detail lấy metadata — dùng cho "Thăm dò"), `DouyinCookieExpiredError` khi gặp 401/403 — **viết theo cơ chế công khai, chưa chạy được với dữ liệu thật** vì thiếu cookie + URL mẫu.
- [x] Cơ chế phát hiện cookie hết hạn → báo UI — **đã nối lên API/UI** (409 riêng, khác 400 của "chưa có cookie"), test bằng mock. Chưa gặp cookie hết hạn thật.
- [x] `app/services/cost_service.py` + `POST /api/jobs/{id}/cost-estimate` — verify bằng request thật: job free (Google/Edge-TTS) ra $0, job có cấu hình OpenAI key ra chi phí ước tính khác 0 đúng công thức.
- [x] Fallback provider khi lỗi/hết quota — đã làm ở Phase 2 (`translate_service`, `tts_service`), không cần làm lại.
- [x] UI chọn nền tảng Bilibili/Douyin — **đã có** (2 nút ở thẻ "Tạo job crawl"). Chọn Douyin hiện panel riêng nói rõ mức hỗ trợ hiện tại, không giả vờ như Bilibili.
- [x] **`DouyinClient.download_no_watermark()` + `douyin_service.download_video()`** (2026-09-15 sáng) — tải video không watermark bằng **yt-dlp** thay vì tự bóc tách JSON. 8 test mới (mock `yt_dlp.YoutubeDL`/`DouyinClient`). **Chưa gọi thật** — cần cookie + URL mẫu.
- [ ] Nối `download_video()` vào pipeline (`app/api/pipeline.py`, hiện `_run_download` chỉ gọi thẳng `BilibiliClient`, chưa rẽ nhánh theo `video.platform`) + luồng tạo job Douyin từ link share trên UI — **chưa làm, ngoài phạm vi phiên này** (cần verify `download_video()` chạy thật trước, tránh nối dây một hàm chưa kiểm chứng được vào pipeline chính).
- [x] **Tìm kiếm từ khoá — hạ tầng ký `a_bogus` + phát hiện "cần đăng nhập"** (2026-09-15 chiều) — `app/adapters/douyin/_vendor_abogus.py` (vendor từ f2), `app/adapters/douyin/search.py` (`probe_search()`), `douyin_service.search_videos()`, endpoint `POST /api/jobs/douyin/search-probe`. **Đã verify bằng request thật** (không phải đoán): chữ ký đúng cú pháp, nhưng Douyin chặn ở tầng nghiệp vụ với `status_code=2483` ("vui lòng đăng nhập"). 13 test mới, mock ở mức `httpx`/`probe_search` (không gọi mạng thật trong CI).
- [ ] **Đọc kết quả tìm kiếm thành công** (parse response thật thành danh sách video, lưu vào Job/Video như `crawl_service.py` làm cho Bilibili) — **chưa làm**, vì hình dạng JSON lúc thành công hoàn toàn chưa biết (chưa từng thấy response thành công), cần cookie đăng nhập thật để thăm dò trước — xem "Việc tiếp theo" trong Ghi chú 2026-09-15 chiều.

## Tiêu chí hoàn thành (Definition of Done)
- [ ] Crawl + tải được video Douyin không watermark — code đã viết xong (giao cho yt-dlp) và unit-test đầy đủ, **nhưng chưa chạy thật + chưa nối vào pipeline chính**, cần cookie ẩn danh + URL mẫu thật từ bạn để verify.
- [ ] Tìm kiếm theo từ khoá ra danh sách video (mục tiêu gốc "nhập từ khoá/chủ đề → crawl") — hạ tầng ký request xong & verify thật, nhưng **bị chặn ở bước cần cookie đăng nhập tài khoản thật** + chưa biết hình dạng JSON thành công. Đây là hạng mục rủi ro cao nhất Phase 3: phụ thuộc thuật toán `a_bogus` do ByteDance chủ động thay đổi định kỳ để chặn scraper (đã được thông báo trước khi làm, xem Ghi chú).
- [x] Chạy pipeline với ít nhất 2 provider khác nhau cho cùng 1 tác vụ — đã có từ Phase 2 (OpenAI/Google, ElevenLabs/Edge-TTS), tự đổi qua lại theo key đã cấu hình (không phải chọn tay qua UI, nhưng đáp ứng đúng ý ban đầu "ưu tiên key trả phí nếu hoạt động").
- [x] Thấy cảnh báo ước tính chi phí trước khi chạy batch — verify qua `POST /api/jobs/{id}/cost-estimate`, có field `warning` khi chi phí ước tính vượt ngưỡng $1.
- [ ] Cookie Douyin hết hạn được phát hiện và báo rõ ràng — code đã có (`DouyinCookieExpiredError`, giờ bắt cả lỗi "fresh cookies" của yt-dlp), chưa verify được vì chưa có cookie thật để tạo tình huống hết hạn.

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

### Phiên 2026-09-15 sáng — chuyển sang yt-dlp cho phần tải, xoá bỏ hiểu nhầm "cần đăng nhập"

**Lý do đổi hướng:** người dùng hỏi có cách nào khác lấy video Douyin ngoài việc tự
viết adapter + cần cookie cá nhân. Research 3 hướng (yt-dlp, cookie khách qua
Playwright, dịch vụ bóc video bên thứ 3) → chọn yt-dlp vì cộng đồng lớn liên tục vá
theo mỗi lần Douyin đổi cơ chế chống bot, đỡ việc tự dò lại endpoint như lo ngại ở
phiên trước ("Douyin đổi API khá thường xuyên").

**Đã verify bằng lệnh gọi thật, không phải suy luận từ tài liệu:**
1. Cài `yt-dlp` (2026.8.19) vào scratchpad, đọc source `yt_dlp/extractor/tiktok.py`
   → `DouyinIE` gọi **đúng endpoint** `aweme/v1/web/aweme/detail/` mà
   `DouyinClient.get_video_detail()` đã viết từ trước — tự tin hơn là adapter cũ đi
   đúng hướng, không phải đoán mò.
2. Chạy thật `yt_dlp.YoutubeDL().extract_info()` với URL test mẫu của chính yt-dlp
   (`douyin.com/video/6961737553342991651`), **không cookie** → lỗi giống hệt dự
   đoán: `"Fresh cookies (not necessarily logged in) are needed"`. Tức là **yt-dlp
   không né được việc cần cookie** — chỉ đỡ việc tự viết code bóc JSON (điều này
   quan trọng, tránh ảo tưởng yt-dlp là "cách khác không cần cookie").
3. Đọc source: cookie cần thiết là **`s_v_web_id`** — cookie ẩn danh do JS challenge
   sinh ra khi trình duyệt mở trang, **không phải cookie phiên đăng nhập tài khoản**.
   yt-dlp code có comment `TODO: Run verification challenge code to generate
   signature cookies` — tức chính yt-dlp cũng chưa tự động hoá bước này, vẫn cần
   cookie lấy từ trình duyệt thật.
4. yt-dlp **không có extractor riêng cho link share `v.douyin.com`** — chỉ khớp URL
   dạng `douyin.com/video/<id>`. Vì vậy giữ nguyên `resolve_share_url()` (httpx,
   không cần cookie vì chỉ là theo redirect công khai) làm bước tiền xử lý trước khi
   đưa URL cho yt-dlp, thay vì trông chờ yt-dlp tự follow redirect của link share.

**Đã làm:**
- Thêm `yt-dlp>=2026.8` vào `backend/requirements.txt`.
- `DouyinClient.download_no_watermark(aweme_id, dest_path, cookie)` — gọi
  `yt_dlp.YoutubeDL` đồng bộ (blocking), truyền cookie qua `http_headers={"Cookie":
  ...}` (đúng cơ chế "compat" chính thức của yt-dlp — tự nạp vào cookiejar rồi bỏ
  khỏi header, xem `YoutubeDL._load_cookies`). Bắt `yt_dlp.utils.DownloadError`
  chứa "cookies" → ném lại `DouyinCookieExpiredError` (đồng nhất với lỗi 401/403 cũ,
  UI không cần phân biệt 2 nguồn lỗi).
- `douyin_service.download_video(share_url, dest_path)` — resolve trước rồi gọi hàm
  trên qua `asyncio.to_thread` (theo đúng convention `asyncio.to_thread` đã dùng ở
  `storage_cleanup_service.py`, vì yt-dlp là thư viện đồng bộ).
- 8 test mới (`tests/adapters/test_douyin_client.py` +
  `tests/services/test_douyin_service.py::TestDownloadVideo`), mock ở mức
  `yt_dlp.YoutubeDL`/`DouyinClient` — không gọi mạng thật (cần cookie thật, không
  chạy được trong CI). Toàn bộ 377 test backend pass.

**Cố ý CHƯA làm (ngoài phạm vi phiên này):** nối `download_video()` vào
`app/api/pipeline.py` — file này hiện hoàn toàn hard-code Bilibili (`_run_download`
gọi thẳng `BilibiliClient`, không rẽ nhánh theo `video.platform`), và UI Douyin mới
dừng ở "dán link thăm dò", chưa có luồng tạo job từ link share. Nối dây đầy đủ là
việc lớn hơn "áp dụng yt-dlp", và nối một hàm tải video chưa từng chạy thật vào
pipeline chính là rủi ro không cần thiết — nên làm sau khi có cookie thật để verify
`download_video()` trước.

**Việc tiếp theo khi có cookie + 1 link share thật:**
1. Dán cookie vào `DOUYIN_COOKIE` trong `backend/.env`.
2. Gọi thử `douyin_service.download_video(share_url, Path("test.mp4"))` (script nhỏ
   hoặc qua Python REPL) — xem tải được file mp4 không watermark thật không.
3. Nếu OK: rẽ nhánh `video.platform` trong `pipeline.py::_run_download`, thêm luồng
   tạo job Douyin từ link share ở `douyin-panel.tsx` (hiện chỉ có nút "Thăm dò").
4. Nếu yt-dlp báo lỗi khác "fresh cookies" (ví dụ Douyin đổi endpoint lần nữa): việc
   cần làm là `pip install -U yt-dlp` trước (nhiều khả năng cộng đồng đã vá), không
   phải tự sửa code — đây chính là lợi ích chọn yt-dlp thay vì tự viết.

### Phiên 2026-09-15 chiều — tìm kiếm từ khoá: vendor `a_bogus`, phát hiện cần đăng nhập thật

**Bối cảnh:** người dùng xác nhận muốn "làm full luồng Douyin" (từ khoá → video,
giống Bilibili), chấp nhận đánh đổi đã cảnh báo trước: tìm kiếm/danh sách kênh trên
Douyin đòi ký request bằng thuật toán chống bot `a_bogus`/`X-Bogus` do ByteDance
cố tình đổi định kỳ — khác hẳn phần tải video (chỉ cần cookie).

**Research 3 nguồn cho a_bogus:** [f2](https://github.com/Johnserf-Seed/f2)
(Apache-2.0, có `ABogusManager` + model `PostSearch` sẵn — README tự nhận tính
năng search 🔵 "chưa xong" nhưng model/thuật toán ký thì có thật), Evil0ctal
Douyin_TikTok_Download_API (bản v5 mới nhất không còn liệt kê search là tính
năng chính, chỉ chạy được dạng Docker/FastAPI service riêng — không hợp để
nhúng thẳng vào backend mình), tự viết signature (loại ngay — quá phức tạp,
rủi ro sai không kiểm chứng được).

**Quyết định: vendor 1 file thuật toán từ f2, KHÔNG `pip install f2`.** Lý do:
`f2` là tool CLI đầy đủ tính năng, kéo theo ~20 dependency nặng không liên quan
(rich, click, qrcode, pyexecjs cần Node.js, browser-cookie3, aiosqlite,
protobuf...) — không đáng gánh vào bundle desktop (Phase 12) chỉ để dùng 1
thuật toán ký tự thân tự đủ. Đã kiểm tra: `f2/utils/abogus.py` (class `ABogus`,
`BrowserFingerprintGenerator`, `CryptoUtility`, `StringProcessor`) chỉ phụ
thuộc `gmssl` (BSD, pure-Python, nhẹ) + thư viện chuẩn — tách ra được sạch sẽ.
Đã copy gần như nguyên văn vào `app/adapters/douyin/_vendor_abogus.py` (chỉ bỏ
khối demo `__main__`), giữ nguyên logic bit-shift/mảng số (không "dọn code"
thuật toán người khác — rủi ro gây sai mà không ai phát hiện được).

**Đã verify bằng request thật tới douyin.com (không phải suy luận):**
1. Dựng URL tìm kiếm ký bằng `ABogus` + field từ `f2.apps.douyin.model.PostSearch`
   (đối chiếu source thật để lấy đúng bộ tham số bắt buộc — `device_platform`,
   `aid`, `browser_*`, `msToken`...; không đoán tham số).
2. Gọi thật `aweme/v1/web/general/search/single/`, **không cookie** →
   **HTTP 200** với `{"status_code":2483,"status_msg":"请先登录，再继续搜索吧"}`
   ("vui lòng đăng nhập trước khi tìm kiếm"). Không phải lỗi 403/405 ở tầng
   chống bot — nghĩa là **chữ ký `a_bogus` đúng cú pháp**, request được xử lý
   tới tầng nghiệp vụ, và tầng đó đòi *đăng nhập tài khoản thật*.
3. **Phát hiện quan trọng nhất:** cookie ẩn danh (`s_v_web_id`, đủ cho tải
   video) **KHÔNG đủ cho tìm kiếm**. Đây là 2 loại cookie khác nhau về bản
   chất, không phải cùng 1 thứ dùng chung được — sửa lại giả định ban đầu của
   phiên sáng rằng "Douyin không cần đăng nhập" (đúng cho tải video, sai cho
   tìm kiếm).
4. Test thêm: msToken **tự sinh ngẫu nhiên tại chỗ** (không gọi endpoint sinh
   token thật của Douyin) vẫn nhận **cùng phản hồi** — nghĩa là bước này Douyin
   không kiểm tra tính xác thực của msToken chặt, tự sinh giả là đủ. Nhờ vậy
   không cần vendor thêm phần `TokenManager.gen_real_msToken()` của f2 (phần đó
   gọi mạng thật, phức tạp hơn, phụ thuộc nhiều lớp nội bộ khác của f2) — giữ
   phần vendor gọn nhất có thể.

**Đã làm:**
- `app/adapters/douyin/_vendor_abogus.py` — vendor thuật toán (chi tiết ở trên).
- `app/adapters/douyin/search.py`: `_gen_fake_ms_token()`, `_sign()`,
  `probe_search(keyword, cookie)` — gọi thật, phân loại `status_code`:
  `2483` → `DouyinLoginRequiredError` (lỗi mới, khác `DouyinCookieExpiredError`
  vì hành động cần làm khác hẳn — đăng nhập thật, không chỉ mở trang copy
  cookie), khác 0 → `DouyinSearchError` (chưa gặp thật, giữ nguyên message
  Douyin để dễ tra khi gặp), 0 → trả JSON thô (hình dạng thành công chưa biết).
- `douyin_service.search_videos()` + endpoint `POST /api/jobs/douyin/search-probe`
  — cùng pattern "probe" như `probe_share_url()`, HTTP 409 khi cần đăng nhập
  (kèm giải thích rõ khác cookie ẩn danh), 502 khi lỗi nghiệp vụ khác.
- Thêm `gmssl>=3.2` vào `requirements.txt` (dependency duy nhất mới, nhẹ).
- 13 test mới (`tests/adapters/test_douyin_search.py` +
  `tests/services/test_douyin_service.py::TestSearchVideos`) — mock
  `httpx`/`probe_search`, không gọi mạng thật trong CI. Toàn bộ 388 test
  backend pass, ruff sạch.

**Cố ý CHƯA làm:** đọc/parse kết quả tìm kiếm thành công (danh sách video), lưu
vào Job/Video như `crawl_service.py` làm cho Bilibili, UI ô nhập từ khoá cho
Douyin. Lý do giống hệt lý do trì hoãn phần bóc tách video ở phiên trước: hình
dạng JSON lúc **thành công** hoàn toàn chưa biết (mọi lần gọi thật cho tới giờ
đều dừng ở "cần đăng nhập", chưa từng thấy response có dữ liệu) — viết code đọc
theo phỏng đoán sẽ tạo ra thứ không ai kiểm chứng được.

**Cập nhật ngay sau đó cùng ngày — BLOCKED, tạm dừng:** hỏi lại thì bạn cho biết
**không có tài khoản Douyin**. Đưa ra 3 hướng: (1) tạo tài khoản mới miễn phí chỉ
để lấy cookie, (2) bỏ tìm kiếm từ khoá, quay về "dán link" (đã hoạt động, không
cần tài khoản), (3) tạm dừng quyết định. Bạn chọn **(3) tạm dừng** — không đầu tư
thêm cho `search.py`/`_vendor_abogus.py` cho tới khi bạn chủ động quay lại với
quyết định mới (có tài khoản, hoặc đổi hướng sang "dán link"). Code + test hiện
tại giữ nguyên làm hạ tầng sẵn sàng, không phải xoá.

**Việc tiếp theo khi có cookie đăng nhập thật (chỉ làm khi bạn quay lại):**
1. Đăng nhập 1 tài khoản Douyin thật trên trình duyệt (khuyến nghị dùng tài
   khoản phụ — cookie đăng nhập nhạy cảm hơn cookie ẩn danh), lấy cookie qua
   DevTools, dán vào `DOUYIN_COOKIE`.
2. Gọi `POST /api/jobs/douyin/search-probe` với 1 từ khoá bất kỳ — nếu vẫn
   nhận 409 nghĩa là cookie chưa đúng dạng đăng nhập (thiếu `sessionid` chẳng
   hạn) hoặc phiên đăng nhập đã hết hạn, thử đăng nhập lại.
3. Nếu nhận JSON có dữ liệu: đưa hình dạng JSON (`status_code`, top-level keys,
   1 item mẫu trong danh sách kết quả) vào phiên sau → viết phần đọc kết quả
   có căn cứ + nối vào `crawl_service.py`/UI.
4. Nếu `a_bogus` bắt đầu bị chặn ở tầng chống bot (403/405 thay vì
   "status_code":2483) — dấu hiệu ByteDance đã đổi thuật toán: việc cần làm là
   lấy lại bản mới nhất của `f2/utils/abogus.py` từ
   [github.com/Johnserf-Seed/f2](https://github.com/Johnserf-Seed/f2) rồi dán
   đè `_vendor_abogus.py` (xem cảnh báo bảo trì ở đầu file đó) — đây chính là
   khoản "nợ bảo trì dài hạn" đã được cảnh báo trước khi bắt đầu vendor.
