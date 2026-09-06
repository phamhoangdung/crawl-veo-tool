# Tool crawl + lồng tiếng AI cho video Bilibili/Douyin

## Context
Bạn muốn xây một tool cá nhân: nhập từ khoá/chủ đề → crawl và tải video từ Bilibili, Douyin (không dính watermark) → sau đó dịch và lồng tiếng video bằng API key của các model AI (hoặc tự nhập kịch bản để tool gen giọng đọc). Bạn dùng https://www.nguyenhieuai.com (GOHA) làm hình mẫu về giao diện/trải nghiệm.

**Lưu ý quan trọng phát hiện khi research:** GOHA thực chất là SaaS tạo video bằng Veo 3.1 (sinh video AI) + xoá watermark Veo/Gemini + upscale, **không phải** tool crawl Bilibili/Douyin. Vì vậy phần "giống tool này" nên hiểu là học theo **kiểu giao diện/luồng vận hành** (dashboard, xử lý hàng loạt theo hàng đợi, các module dạng tab, theo dõi tiến trình/lỗi) — còn phần tính năng lõi (crawl 2 nền tảng, dịch, lồng tiếng) là phần bạn tự định nghĩa và được triển khai riêng dưới đây.

Quyết định đã chốt cùng bạn:
- **Nền tảng chạy**: Web app local (backend Python + giao diện web), không phải desktop app hay CLI thuần.
- **Tích hợp AI**: đa nhà cung cấp ngay từ đầu (OpenAI, Google, ElevenLabs, Azure, DeepL, Edge-TTS...), chọn provider theo từng tác vụ.
- **Xử lý âm thanh**: tách và giữ nhạc nền gốc, chỉ thay giọng nói (không xoá sạch track âm thanh).
- **Đầu ra**: vừa lồng tiếng vừa xuất phụ đề song ngữ (.srt gốc + dịch), có tuỳ chọn burn-in.

**Đã chốt về mô hình sử dụng**: giai đoạn đầu dùng cho chính bạn, sau khi ổn định và bổ sung thêm tính năng sẽ đóng gói để bán cho người khác. Vì vậy dù MVP chỉ có 1 người dùng, các quyết định schema/kiến trúc dưới đây được thiết kế sẵn để không phải refactor lớn khi chuyển sang multi-user:
- Bảng API key, job, video trong DB có field `user_id`/`workspace_id` ngay từ đầu (dù MVP chỉ có 1 giá trị cố định) — tránh phải thêm cột và migrate dữ liệu cũ khi có user thứ 2.
- Mỗi user tự quản lý API key riêng của mình (không dùng chung 1 bộ key global) — đúng mô hình sản phẩm bán ra sau này, mỗi khách tự nhập key của họ.
- **Lưu ý pháp lý tăng thêm khi có ý định bán**: khi chỉ dùng cá nhân, rủi ro pháp lý (ToS Bilibili/Douyin, bản quyền nội dung tải về) chủ yếu bạn tự chịu; khi đóng gói bán cho người khác, rủi ro mở rộng ra cả việc bạn cung cấp công cụ/dịch vụ giúp người khác vi phạm ToS/bản quyền nền tảng gốc — nên cân nhắc điều khoản sử dụng (ToS) riêng cho sản phẩm, giới hạn trách nhiệm, và có thể cần tư vấn pháp lý trước khi thương mại hoá chính thức.

**Đã chốt nền tảng & ngôn ngữ**: làm Bilibili trước (ít cần cookie/anti-bot hơn Douyin, không có watermark overlay cứng, phù hợp để có MVP chạy nhanh và test AI pipeline trước khi đụng tới Douyin phức tạp hơn); cặp ngôn ngữ chính là **Trung → Việt**. Toàn bộ 3 gate đã chốt, xem chi tiết ở mục "Việc cần chốt" cuối file.

## Kiến trúc tổng thể
- **Backend**: Python 3.11+, FastAPI — vì gần như toàn bộ hệ sinh thái mã nguồn mở cần dùng (download engine, Whisper, tách nhạc nền, TTS local) đều là Python.
- **Frontend**: React + Vite + TypeScript + Tailwind + shadcn/ui, dựng trên khung template [satnaing/shadcn-admin](https://github.com/satnaing/shadcn-admin) (12K+ sao, MIT) — có sẵn layout sidebar + topbar, dark/light mode, 10+ trang mẫu. Sidebar ánh xạ trực tiếp theo module: Crawl & Download, Trend Discovery, Jobs/Batch monitor, Library, Cài đặt API key/Provider. Chạy tách rời khỏi backend, gọi REST API của FastAPI.
- **DB**: SQLite + SQLAlchemy, bật `PRAGMA journal_mode=WAL` ngay từ đầu (nhiều video xử lý song song update trạng thái cùng lúc dễ gặp "database is locked" nếu không bật WAL) + retry khi ghi. Lưu job, metadata video, trạng thái pipeline, tránh tải trùng (dedup theo video ID).
- **Job/queue**: **không dùng `BackgroundTasks` của FastAPI cho các bước AI nặng** (Whisper/Demucs là tác vụ CPU/GPU-bound, chạy trong `BackgroundTasks` sẽ chặn event loop, không có persistence khi restart app, không giới hạn concurrency, không retry). Ngay từ MVP dùng `ProcessPoolExecutor`/`multiprocessing` cho các bước nặng; cân nhắc chuyển lên Celery/RQ + Redis sớm hơn dự kiến ban đầu (không để tới giai đoạn cuối) vì đổi mô hình job sau này kéo theo đổi luôn schema trạng thái job đã lưu.
- **State machine cho job pipeline**: thiết kế rõ các trạng thái/transition của 1 video qua pipeline (queued → downloading → downloaded → separating_audio → transcribing → translating → dubbing → muxing → done / failed_at_<step>) và cách resume khi 1 bước fail giữa chừng, **thiết kế trước khi tạo bảng job trong DB** — tránh phải sửa lại schema khi thêm error handling sau này.
- **File storage**: thư mục theo `job_id/video_id/` chứa video gốc, audio tách (vocal/nhạc nền — thiết kế cấu trúc hỗ trợ multi-track ngay từ đầu dù bước tách nhạc nền làm ở giai đoạn sau), transcript, bản dịch, audio lồng tiếng, video output, phụ đề.
- **ffmpeg** là dependency bắt buộc (mux audio/video, merge DASH stream của Bilibili, burn phụ đề).
- **Adapter interface cho provider AI** (`translate()`, `transcribe()`, `tts()`) cần có capability flags ngay từ đầu (giới hạn ký tự/request, ngôn ngữ hỗ trợ, streaming vs batch...) để tránh phải sửa lại interface khi thêm provider thứ 2-3.
- **Downloader phụ thuộc thư viện bên thứ 3** ([Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)) — nên pin version hoặc fork riêng thay vì phụ thuộc trực tiếp upstream, vì repo đó cũng có thể đổi/break theo Bilibili/Douyin; kèm cơ chế self-test định kỳ (health-check) để phát hiện sớm khi nền tảng đổi API, thay vì chờ user report lỗi.

## Danh sách module & tính năng cần làm

### 1. Module Crawl & Download (Bilibili + Douyin)
- Nhập từ khoá/chủ đề → gọi search endpoint của từng nền tảng → liệt kê kết quả (thumbnail, tiêu đề, tác giả, view, thời lượng) để chọn thủ công hoặc auto-lấy top N.
- Tải không watermark:
  - **Douyin**: watermark là overlay do app chèn khi share, cần lấy trực tiếp `play_addr` gốc qua endpoint mobile/web API (không phải link share công khai). Tham khảo cách làm ở dự án mã nguồn mở [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) (hỗ trợ sẵn Douyin/TikTok/Kuaishou/Bilibili, async, có sẵn cơ chế no-watermark) — nên tái sử dụng ý tưởng/thư viện thay vì viết lại từ đầu.
  - **Bilibili**: video gốc thường không có watermark logo cứng của nền tảng; cần xử lý stream DASH (video/audio tách riêng, merge bằng ffmpeg). Nếu video có logo do chính uploader chèn cứng thì không thể "xoá" tự động bằng cách tải khác — việc xoá logo kiểu này (nếu thực sự cần) là bài toán inpainting riêng (vd LaMa), nên để thành tính năng optional/giai đoạn sau, không gộp vào MVP.
  - Douyin nhiều endpoint cần cookie hợp lệ → cần cơ chế nhập/refresh cookie trong tool, **và tự phát hiện cookie hết hạn** (lỗi 401/403 lặp lại nhiều lần liên tiếp) để báo UI yêu cầu refresh thay vì để job fail âm thầm.
  - Rate limit, retry, xử lý video riêng tư/đã xoá, chống bị chặn (đổi User-Agent, delay).
- Batch theo từ khoá: hàng đợi tải, progress bar theo từng video, log lỗi riêng từng video, cho phép resume/retry job lỗi.
- Dedup theo video ID để không tải lại video đã xử lý.

### 2. Module Khám phá xu hướng (Trend Discovery)
- Mục tiêu: biết hiện đang có chủ đề/video nào đang hot trên Bilibili (và sau này Douyin) để chọn làm từ khoá crawl, thay vì phải tự đoán/tự vào app xem thủ công.
- **Bilibili (làm trước, ưu tiên MVP-0 vì miễn phí, không cần key)**:
  - `https://api.bilibili.com/x/web-interface/popular` — video phổ biến chung.
  - `https://api.bilibili.com/x/web-interface/ranking/region?rid={rid}&day={day}` — bảng xếp hạng theo từng phân khu (category) + khoảng thời gian.
  - Tham khảo tài liệu API đầy đủ tại [SocialSisterYi/bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect) (repo cộng đồng rất uy tín, tổng hợp toàn bộ endpoint Bilibili).
- **Douyin (làm sau, khó hơn)**: không có API trending công khai dễ dùng — các endpoint cần chữ ký (signature) phức tạp và dễ bị chặn khi gọi từ ngoài Trung Quốc. Hướng khả thi là dùng dịch vụ trung gian trả phí (vd TikHub) để lấy hot/rising video, hot search, hot topic — cần cân nhắc chi phí trước khi làm, không bắt buộc ở MVP.
- Trang "Khám phá xu hướng" trong Dashboard: hiển thị danh sách trending theo nền tảng/category, có nút "Dùng làm từ khoá crawl" đẩy thẳng sang Module Crawl.
- Lưu snapshot trending theo thời gian (vd mỗi vài giờ) vào DB để theo dõi xu hướng lên/xuống, không chỉ xem tức thời.
- Polling theo chu kỳ hợp lý (không quá dày) để tránh rate limit từ API Bilibili.

### 3. Module xử lý AI (Transcribe → Dịch → Lồng tiếng → Ghép)
- **Transcribe**: Whisper (local qua `faster-whisper` để chạy nhanh hơn, hoặc gọi OpenAI Whisper API) → transcript kèm timestamp theo câu/đoạn.
- **Video dài/nhiều tập**: Whisper và Demucs tốn RAM/VRAM lớn với file dài — cần chunk theo khoảng lặng (silence-based split) trước khi transcribe/tách nhạc thay vì xử lý nguyên file.
- **Tách âm thanh nền**: Demucs (Meta, mã nguồn mở) tách vocal / nhạc nền — giữ lại track nhạc nền để mix lại sau.
- **Dịch kịch bản**: gọi provider AI đã chọn (GPT/Gemini/DeepL...), dịch theo từng câu và giữ mốc thời gian.
- **Chế độ nhập kịch bản thủ công**: cho phép dán/sửa trực tiếp bản dịch (bỏ qua bước auto-translate) trước khi generate giọng đọc — đúng yêu cầu "đưa kịch bản vào tool sẽ gen tiếng".
- **TTS/lồng tiếng**: gọi provider TTS đã chọn, sinh audio theo từng câu; time-stretch (co giãn nhẹ) để khớp thời lượng với đoạn gốc.
- **Ghép**: mix giọng đọc mới với track nhạc nền đã tách, mux lại vào video gốc bằng ffmpeg.
- **Phụ đề song ngữ**: xuất `.srt`/`.vtt` (gốc + dịch), tuỳ chọn burn-in vào video.
- **Hardsub trên video gốc**: nhiều video Bilibili/Douyin (đặc biệt video Trung) có phụ đề cứng sẵn — nếu burn thêm phụ đề song ngữ mới dễ bị chồng chữ. Cần cảnh báo user khi phát hiện (thủ công hoặc OCR đơn giản) và cho tuỳ chọn vị trí đặt phụ đề mới (trên/dưới) để tránh đè lên hardsub.
- **Tỉ lệ khung hình khác nhau**: Douyin chủ yếu 9:16, Bilibili đa dạng tỉ lệ (16:9, 4:3...) — ảnh hưởng font size/vị trí khi burn-in phụ đề, cần thiết kế template phụ đề theo tỉ lệ thay vì cố định 1 kiểu.
- **Version pin cho model AI**: Whisper/GPT model có thể đổi version theo thời gian khiến kết quả không lặp lại được giữa các lần chạy — nên pin version cụ thể trong config thay vì luôn gọi "latest".

### 4. Module quản lý API key / Provider AI & bảo mật
- UI nhập & lưu API key theo từng provider (OpenAI, Google Translate/Cloud TTS, ElevenLabs, Azure Speech, DeepL, Edge-TTS không cần key...).
- **Bảo mật secret cụ thể** (không chỉ ghi chung chung "mã hoá"): dùng master key riêng lưu ở biến môi trường/`.env` không commit vào git, mã hoá key theo kiểu Fernet/AES trước khi lưu DB, mask key khi hiển thị trên UI (chỉ show vài ký tự cuối). Làm ngay từ MVP, không để tới bước sau — vì MVP đã cần nhập key thật để test TTS/dịch, nếu không có cơ chế an toàn ngay từ đầu dễ dẫn tới lưu key dạng plaintext tạm rồi quên nâng cấp.
- Thiết kế theo kiểu adapter: mỗi provider implement chung interface (`translate()`, `transcribe()`, `tts()`, kèm capability flags — xem phần Kiến trúc) để thêm provider mới dễ dàng, không sửa core.
- Cho chọn provider mặc định theo từng tác vụ (dịch dùng provider nào, giọng đọc dùng provider nào) + fallback khi provider lỗi/hết quota.
- **Kiểm soát chi phí trước khi chạy, không chỉ theo dõi sau**: thêm bước ước tính chi phí (dry-run estimate) trước khi submit 1 batch — ví dụ chạy 100 video qua ElevenLabs có thể tốn rất nhiều tiền chỉ trong 1 lần bấm nút. Nên có budget cap theo job (cảnh báo hoặc chặn khi vượt ngưỡng đã đặt) bên cạnh việc theo dõi usage đã chạy.

### 5. Module Dashboard / UI (theo hướng giống GOHA)
- **Về tham khảo GOHA**: trang nguyenhieuai.com chỉ là landing page marketing (hero, card tính năng, bảng giá, FAQ, light mode, tối giản) — không lộ chi tiết UI *bên trong app* (dashboard theo dõi batch/queue thực tế). Chỉ dùng được làm cảm hứng tổng thể (sạch, sáng màu, hiện đại), phần layout dashboard cụ thể tự thiết kế dựa trên template dưới đây.
- **Template khởi điểm**: [satnaing/shadcn-admin](https://github.com/satnaing/shadcn-admin) (React + Vite + TypeScript + shadcn/ui + Tailwind, sidebar + topbar, dark/light mode). Sidebar ánh xạ theo module:
  - Trang tạo job: nhập từ khoá + chọn nền tảng + cấu hình pipeline (ngôn ngữ đích, provider dịch/giọng đọc, có tách nhạc nền hay không, có burn phụ đề hay không).
  - Trang Trend Discovery: danh sách trending Bilibili/Douyin, nút "Dùng làm từ khoá crawl".
  - Trang theo dõi batch: trạng thái từng video qua các bước (đã tải / đã tách audio / đã dịch / đã lồng tiếng / hoàn tất), log lỗi.
  - Trang preview & chỉnh sửa: nghe/xem thử, sửa transcript hoặc bản dịch trước khi render lồng tiếng.
  - Trang thư viện: danh sách video đã xử lý, tải lẻ hoặc tải hàng loạt (zip).
  - Trang cài đặt: quản lý API key/provider theo user (mask key, chọn provider mặc định theo tác vụ).

### 6. Hạ tầng & vận hành
- Cấu hình giới hạn số job/video xử lý song song (tránh quá tải máy cá nhân, đặc biệt khi chạy Whisper/Demucs).
- GPU là optional để tăng tốc Whisper/Demucs; cần fallback chạy được trên CPU (chậm hơn).
- Logging tập trung để debug khi Bilibili/Douyin đổi API (rất hay xảy ra với API không chính thức).
- **Quản lý dung lượng lưu trữ**: video gốc + audio tách + TTS output tích luỹ rất nhanh (hàng chục GB nếu chạy batch lớn) — cần retention policy (tự xoá file trung gian sau X ngày, hoặc giới hạn tổng dung lượng job) thay vì để tích luỹ vô hạn.
- **Testing strategy**: ngoài smoke test thủ công end-to-end, cần unit test cho từng adapter provider, test khớp timestamp `.srt` với audio, và health-check định kỳ để phát hiện sớm khi Bilibili/Douyin đổi API.
- **Packaging/môi trường (đặc biệt trên Windows)**: cần chốt cách cài đặt — `requirements.txt`/lockfile, cách cài ffmpeg binary trên Windows, driver GPU (CUDA) nếu dùng GPU cho Demucs/Whisper — nhiều thư viện Python ML có vấn đề cài đặt riêng trên Windows nên cần test sớm, không để tới lúc deploy mới phát hiện.

### 7. Lưu ý pháp lý/rủi ro (không chặn kế hoạch, nhưng cần biết trước)
- Bilibili/Douyin đều có điều khoản cấm scraping/tải hàng loạt tự động; endpoint không chính thức có thể bị đổi hoặc chặn bất kỳ lúc nào → thiết kế download layer tách biệt (adapter riêng theo nền tảng) để dễ vá khi bị đổi.
- Nội dung tải về thuộc sở hữu người đăng gốc; dịch/lồng tiếng rồi đăng lại nơi khác có thể vướng bản quyền nếu dùng cho mục đích thương mại/công khai mà không xin phép — nên có bước ghi chú nguồn gốc video trong metadata để kiểm soát rủi ro.

## Đề xuất công nghệ cụ thể (tham khảo khi implement)
- Backend: FastAPI + SQLAlchemy + SQLite (WAL mode), `faster-whisper`, `demucs`, `ffmpeg-python`, `ProcessPoolExecutor`/Celery+Redis cho job nặng.
- Download engine: tham khảo/tái sử dụng [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) (MIT license) — pin version/fork riêng.
- Dịch: OpenAI GPT / Google Translate API / DeepL — chọn theo key sẵn có.
- TTS: ElevenLabs (chất lượng cao, có phí, hỗ trợ multilingual) / Azure hoặc Google Cloud TTS (giọng tiếng Việt tốt) / Edge-TTS (miễn phí) — nên ưu tiên test chất lượng giọng tiếng Việt nếu đích lồng tiếng là tiếng Việt.
- Frontend: React + Vite + TypeScript + Tailwind + shadcn/ui, khởi điểm từ template [satnaing/shadcn-admin](https://github.com/satnaing/shadcn-admin).

## Roadmap đề xuất
1. **MVP-0 (validate downloader trước)**: crawl + tải Bilibili trước + dedup + batch queue cơ bản — xác nhận downloader ổn định trước khi ghép AI pipeline vào, để không lẫn lộn lỗi downloader (rủi ro cao nhất, phụ thuộc bên ngoài) với lỗi AI pipeline. Làm luôn ở bước này: (a) Module Khám phá xu hướng cho Bilibili (API miễn phí, rẻ để thêm ngay, giúp có từ khoá crawl thực tế thay vì đoán), (b) cơ chế lưu API key an toàn (mã hoá, mask UI), (c) thiết kế cấu trúc thư mục hỗ trợ multi-track audio — cả (b) và (c) ảnh hưởng schema/dữ liệu từ đầu, để dồn xuống sau dễ phải migrate lại.
2. **MVP-1**: ghép AI pipeline cho nền tảng đã có ở MVP-0 — transcribe, dịch, TTS 1 provider, ghép audio đơn giản (chưa tách nhạc nền), UI tối giản chạy được end-to-end. Dùng `ProcessPoolExecutor` cho job nặng ngay từ bước này, không dùng `BackgroundTasks` thuần.
3. Thêm nền tảng thứ 2 + đa provider (đủ capability flags) + kiểm soát chi phí trước khi chạy (dry-run estimate, budget cap).
4. Thêm tách nhạc nền (Demucs) + time-stretch canh khớp thời lượng + xử lý video dài (chunk theo khoảng lặng).
5. Thêm phụ đề song ngữ + burn-in (có xử lý hardsub/tỉ lệ khung hình) + trang thư viện quản lý video đã xử lý.
6. Tối ưu batch/queue (cân nhắc Celery/Redis nếu MVP đã chạm giới hạn ProcessPoolExecutor), storage cleanup, retry/error handling nâng cao, health-check định kỳ cho downloader.

## Việc cần chốt trước khi bắt đầu code (đã chốt đủ 3/3, giữ lại làm mốc tham chiếu)
- ~~Làm nền tảng nào trước: Douyin hay Bilibili?~~ **Đã chốt: Bilibili trước.**
- ~~Cặp ngôn ngữ chính?~~ **Đã chốt: Trung → Việt** — ưu tiên test chất lượng giọng TTS tiếng Việt (ElevenLabs multilingual / Azure / Google Cloud TTS / Edge-TTS) ngay từ MVP-1 thay vì để "sau này".
- ~~Tool chỉ chạy local cho riêng bạn, hay cần đóng gói để chia sẻ/bán cho người khác dùng?~~ **Đã chốt**: dùng cho bản thân trước, ổn định + bổ sung tính năng rồi mới đóng gói bán — xem chi tiết ảnh hưởng kiến trúc ở phần Context.

## Kiểm tra khi bắt đầu implement MVP
- Chạy thử pipeline end-to-end với 1 video mẫu: tải về → transcribe → dịch → TTS → mux → so sánh video gốc/video lồng tiếng bằng mắt/tai.
- Kiểm tra dedup hoạt động đúng khi chạy lại cùng từ khoá.
- Kiểm tra phụ đề .srt xuất ra đúng timestamp khớp video.
- Kiểm tra SQLite không bị "database is locked" khi nhiều video chạy song song (xác nhận WAL mode hoạt động).
- Kiểm tra job có thể resume đúng bước khi bị dừng/fail giữa chừng (state machine hoạt động đúng).
