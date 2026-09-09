# Research: Model local & free tier hợp pháp (học từ GOHA Flow Studio)

Ngày: 2026-09-09. Bối cảnh: sau khi phân tích GOHA Flow Studio ([ai-video-generation/research.md](../ai-video-generation/research.md) Phần 6), tách riêng phần "miễn phí" thành tài liệu này vì thuộc pipeline khác (TTS/xử lý ảnh, không phải video-gen).

**Mục đích: tìm hiểu kỹ thuật.** Tài liệu này bàn 3 nhóm:
1. Model chạy local (miễn phí thật, hợp pháp) — TTS tiếng Việt + inpainting xoá watermark.
2. Free tier hợp pháp của provider cloud.
3. Phân tích kiến trúc cơ chế multi-account cookie của GOHA — **chỉ phân tích, cố ý không kèm thiết kế code**, lý do ở Phần 3.

## ⛔ QUYẾT ĐỊNH (2026-09-09): bỏ hướng TTS local

**Chốt: không làm TTS model local.** Lý do: máy hiện tại không có GPU/VRAM ≥ 8 GB, mà đó là ngưỡng tối thiểu để TTS local chạy có ý nghĩa (tác giả GOHA dùng VRAM 11 GB còn nói "chưa ngon"). Chạy CPU thì chậm và chất lượng kém tới mức không dùng được cho sản xuất.

⇒ **Đường đi cho TTS: cloud** — Edge-TTS (đã có, miễn phí) làm mặc định, ElevenLabs (đã có) khi cần chất lượng cao, cân nhắc thêm Gemini TTS free tier nếu muốn style prompt.
⇒ **Voice cloning: cũng bỏ theo** — mọi model clone chất lượng đều cần GPU. Nếu sau này thật cần, đi đường API trả phí (ElevenLabs có voice cloning qua API, không cần GPU của mình).

Phần 1 dưới đây **giữ lại làm tài liệu tham khảo** (phân tích vòng đời model local vẫn đúng và hữu ích nếu sau này đổi máy hoặc cần chạy model nặng khác), nhưng **không nằm trong kế hoạch thực thi**. Phần 2 (free tier) và Phần 3 (phân tích kiến trúc) vẫn còn nguyên giá trị.

## Trạng thái dự án hiện tại (để không đề xuất trùng)

| Hạng mục | Đã có | Chưa có |
|---|---|---|
| TTS | `adapters/tts/edge.py` (Edge-TTS, miễn phí, stateless), `elevenlabs.py` (trả phí) | TTS local chạy model trên máy; voice cloning |
| Tách nhạc nền | `adapters/demucs.py` (Phase 4, model local đã chạy được) | — |
| Xử lý ảnh/video | `adapters/ffmpeg.py`; Phase 13 có che logo bằng vùng mờ (≈ Delogo) | Inpainting thật (cv2/LaMa) |
| Chọn provider TTS | `tts_service.synthesize_speech`: thử ElevenLabs nếu có key → fallback Edge-TTS | Chưa có khái niệm provider cần load model/giữ state |

Điểm đáng chú ý: **`demucs.py` đã là tiền lệ chạy model local trong dự án này** — nghĩa là hạ tầng (torch, quản lý model file, chạy trong ProcessPoolExecutor) đã tồn tại, việc thêm TTS local hay inpainting local rẻ hơn nhiều so với bắt đầu từ 0. Nên đọc `demucs.py` trước khi thiết kế adapter local mới, để dùng lại cùng cách quản lý device/model path.

## Phần 1: TTS local tiếng Việt

### 1.1. Các model GOHA tích hợp (quan sát từ ảnh + transcript)

| Model | Nguồn | Ghi chú từ GOHA |
|---|---|---|
| **VieNeu-TTS** | Model tiếng Việt, chạy CPU/GPU | GOHA ghi "máy bản, miễn phí, CPU/GPU"; ~2-3 GB. Chạy được CPU nhưng chất lượng/tốc độ kém hơn GPU |
| **OmniVoice** (bản fine-tune `KhanhTTS-OmniVoice`) | Model gốc Trung Quốc, fine-tune tiếng Việt bởi cộng đồng VN | ~4-5 GB; GOHA khuyến nghị dùng bản fine-tune tiếng Việt thay vì gốc để đọc chuẩn hơn |
| Gemini TTS | Cloud (free tier / API key) | 30 giọng, hỗ trợ style prompt |
| CapCut TTS | Cloud | 113 giọng — **cần xác minh là API công khai hay reverse-engineer** (xem cảnh báo dưới) |

Tổng dung lượng model local GOHA nêu: ~9-10 GB. Yêu cầu phần cứng thực tế theo tác giả: VRAM 11 GB "vẫn chưa ngon", RAM 64 GB dùng tới 33 GB khi chạy — tức đây là tính năng cho máy khoẻ, không phải mặc định cho mọi người.

⚠ **CapCut TTS**: GOHA gọi là "miễn phí qua server CapCut, siêu nhanh". Cần kiểm tra trước khi tích hợp — nếu đây là endpoint nội bộ của app CapCut bị gọi trực tiếp (không phải API công khai có ToS cho phép), thì cùng nhóm vấn đề với phần cookie ở Phần 3: hợp pháp đáng ngờ, và endpoint có thể đổi bất kỳ lúc nào. **Chưa đưa vào đề xuất tích hợp** cho tới khi xác minh được tài liệu API công khai.

### 1.2. Vấn đề kỹ thuật thật sự: vòng đời model khác hẳn adapter cloud

Đây là phần đáng học nhất. Adapter hiện có (`edge.py`) là **stateless**: mỗi lần gọi mở kết nối, gửi text, nhận audio, xong. Adapter model local thì:

- **Load model tốn 10-60s** và chiếm 2-5 GB RAM/VRAM → không thể load lại mỗi lần synthesize (job đọc truyện 50.000 ký tự chia thành hàng chục đoạn, load lại mỗi đoạn là không dùng được).
- **Không thể load nhiều model cùng lúc** trên máy VRAM hạn chế → cần cơ chế chỉ giữ 1 model trong memory, load model khác thì giải phóng model cũ.
- **Chạy trong ProcessPoolExecutor** (kiến trúc hiện tại) nghĩa là mỗi process con có memory riêng → nếu 3 worker cùng load model TTS là 3× VRAM, tràn ngay. Cần **giới hạn 1 worker cho tác vụ model local**, khác với tác vụ I/O-bound (dịch, download) chạy song song thoải mái.

Cách xử lý đề xuất (theo đúng tiền lệ `demucs.py` đã có trong dự án — cần đọc file đó để xem đã giải quyết ra sao, vì Demucs cũng là model nặng và đã chạy được):

| Vấn đề | Hướng xử lý |
|---|---|
| Load model tốn thời gian | Module-level lazy singleton: giữ model trong biến global của process con, load lần đầu, tái dùng cho các lần gọi sau trong cùng process |
| Nhiều model tranh VRAM | Chỉ cho phép 1 model TTS local hoạt động tại 1 thời điểm; đổi model = unload model cũ (`del` + `torch.cuda.empty_cache()`) rồi load mới |
| Worker song song làm tràn VRAM | Semaphore/queue riêng cho tác vụ dùng GPU (max 1 job đồng thời), tách khỏi pool chung của các tác vụ I/O |
| Máy không đủ VRAM | Kiểm tra VRAM khả dụng **trước khi** nhận job, trả lỗi rõ ràng ("cần ~4 GB VRAM, hiện còn 1.2 GB — dùng provider cloud hoặc đóng ứng dụng khác") thay vì để job chết giữa đường (đây chính là lý do GOHA hiện CPU/GPU/RAM/VRAM trên header) |
| Model chưa tải về | Model file 2-5 GB không nên đóng gói vào app; cần bước tải về lần đầu có progress, và kiểm tra checksum |

### 1.3. Pattern "pluggable model directory" (đáng học)

GOHA: "thả model hợp lệ vào `models/` → hiện ở đây" (ảnh `tts-09`), mặc định `KhanhTTS-OmniVoice`. Nghĩa là danh sách model không hardcode trong code mà **quét thư mục lúc chạy**. Lợi ích: người dùng thêm model fine-tune mới (cộng đồng VN ra model mới liên tục) mà không cần bản cập nhật app.

Áp dụng: `storage/models/tts/<ten-model>/` mỗi thư mục chứa file model + 1 file manifest nhỏ (`model.json`: tên hiển thị, loại, kích thước, yêu cầu VRAM). Service quét thư mục, trả danh sách cho UI. Rẻ để làm, tránh được việc phải sửa code mỗi lần có model mới.

### 1.4. Voice cloning offline

GOHA có 2 tab clone riêng (Clone VieNeu, Clone OmniVoice) + 1 tab "Làm sạch giọng mẫu". Pipeline làm sạch mẫu (ảnh `tts-06`) — **toàn bộ chạy local, dùng được thư viện dự án đã có**:

1. Nhận video/audio bất kỳ → trích audio (`ffmpeg.py` đã có).
2. Tách nhạc nền khỏi giọng (**`demucs.py` đã có sẵn từ Phase 4** — đúng việc nó đang làm).
3. Khử ồn còn lại + chuẩn hoá âm lượng (ffmpeg filter, hoặc thư viện noise reduction).
4. Chọn đoạn 10-20s sạch nhất — GOHA cho user kéo waveform thủ công + có nút tự tìm đoạn. Dự án **đã có `waveform_service.py`** → hạ tầng waveform sẵn rồi.
5. Đưa mẫu sạch vào model TTS để clone.

Nhận xét: bước 1-4 dự án đã có đủ mảnh ghép (ffmpeg + demucs + waveform service), chỉ thiếu bước 5 (model clone) và lớp UI. Đây là ví dụ rõ về việc kiến trúc phân lớp cũ trả lãi.

⚠ Cảnh báo GOHA cũng nêu: chuẩn hoá quá tay (làm dày/EQ mạnh) làm giọng clone nghe giả — mẫu clone chỉ nên xử lý *nhẹ*. Và về pháp lý: clone giọng người khác không xin phép vi phạm quyền nhân thân; GOHA cố ý **không** ship sẵn thư viện giọng clone của người thật. Nếu dự án làm, giữ nguyên nguyên tắc đó + cảnh báo trong UI.

## Phần 2: Free tier hợp pháp của provider cloud

Khác hoàn toàn với "miễn phí bằng cách xoay vòng tài khoản": đây là quota nhà cung cấp *chủ động cho*, dùng bằng 1 tài khoản của chính mình, đúng ToS.

| Provider | Free tier | Dùng cho | Ghi chú |
|---|---|---|---|
| **Edge-TTS** | Không giới hạn thực tế, không cần key | TTS tiếng Việt | **Đã tích hợp** (`adapters/tts/edge.py`) — đây vốn đã là "phần miễn phí" của dự án |
| **Gemini API** | Có free tier (giới hạn request/phút và request/ngày, thay đổi theo thời gian) | Dịch, sửa prompt, TTS (Gemini TTS), sinh ảnh | Quota theo **project** không theo key (xem ai-video-generation/research.md Phần 4) → thêm key không tăng quota |
| **fal.ai** | Credit dùng thử khi đăng ký | Sinh ảnh/video (Phase 14) | Hết credit là hết, không tái tạo |
| **Whisper local** | Miễn phí hoàn toàn | Transcribe | Dự án đã có `transcribe_service.py` — kiểm tra đang dùng local hay API |

Điểm kỹ thuật đáng làm: **free tier có rate limit thấp** (vd vài request/phút) nên cần backoff + queue đúng cách, khác với tài khoản trả phí. `provider_errors.py` (Phase 8) đã nhận diện 429; với free tier cần thêm: đọc header `Retry-After` nếu có, và **hiển thị cho user biết đang bị giới hạn free tier** (chứ không phải lỗi hệ thống) để họ tự quyết có nâng cấp không.

## Phần 3: Cơ chế multi-account cookie của GOHA — phân tích kiến trúc

**Phần này cố ý chỉ phân tích, không kèm thiết kế triển khai.** Lý do: cơ chế này hoạt động bằng cách vượt quota mà Google đặt ra cho Google Flow, vi phạm ToS của Google. Hệ quả thực tế: tài khoản Google bị khoá (rủi ro lan sang tài khoản chính nếu dùng chung máy/IP), và nếu thương mại hoá thì rủi ro pháp lý gắn vào sản phẩm. Phân tích dưới đây để **hiểu hệ thống**, không phải để dựng lại.

### 3.1. Vì sao GOHA buộc phải là desktop app + extension

Đây là câu hỏi kiến trúc thú vị và có câu trả lời kỹ thuật rõ ràng:

- Google Flow (Google Labs) **không có API công khai**. Không có API key nào để mua. Cách duy nhất để gọi được là mạo danh phiên đăng nhập của browser.
- Phiên đăng nhập Google nằm trong **cookie HttpOnly** (`SAPISID`, `__Secure-1PSID`...) — JavaScript trên trang web thường không đọc được (đó chính là mục đích của HttpOnly). Chỉ **extension trình duyệt** (có quyền `cookies` trong manifest) mới đọc được.
- Extension đọc được cookie nhưng không có quyền ghi file / chạy process / quản lý job hàng loạt → cần một **app native** làm chỗ chứa và điều phối.
- ⇒ Kiến trúc bắt buộc: extension (đọc cookie, đẩy về) + desktop app (nhận cookie, gọi API Flow bằng cookie đó, quản lý job/file). Đúng như ảnh `install-12` cho thấy: sidebar "Kết nối Bridge · Online · 5 account · x5 Cookie".

Đây là lý do một web app thuần **không thể** làm được việc này — không phải vì thiếu năng lực kỹ thuật, mà vì mô hình bảo mật của browser cố ý ngăn.

### 3.2. Vì sao "nhiều key" không giải quyết được, phải "nhiều tài khoản"

Đã phân tích ở [ai-video-generation/research.md](../ai-video-generation/research.md) Phần 4, nhắc lại vì liên quan: rate limit Gemini/Veo áp theo **project**, không theo key. Thêm key trong cùng project = chia sẻ cùng quota. Muốn quota độc lập thật phải có project/billing account riêng — với Google Flow (không có API) thì "account riêng" nghĩa là Gmail riêng.

Hệ quả: cơ chế Account Pool hợp pháp của dự án (Phase 8, LRU + cooldown theo key) **hoạt động đúng** với provider kiểu OpenAI/fal.ai/ElevenLabs (1 key = 1 quota), nhưng **không** mở rộng được sang Google theo cách đó. Đây là giới hạn thật của kiến trúc, không phải thiếu sót triển khai — và là lý do Phase 14 chọn fal.ai thay vì gọi Veo trực tiếp.

### 3.3. Các dấu hiệu cho thấy cơ chế này vốn không bền

Quan sát từ chính video của tác giả — hữu ích để hiểu vì sao đây không phải nền tảng đáng đầu tư:

- Tác giả nói Google "thay đổi endpoint liên tục", mỗi lần đổi là tool ngừng hoạt động cho tới khi có bản cập nhật. Đó là bảo trì vĩnh viễn, không phải chi phí một lần.
- UI có checkbox "reCAPTCHA (Flow yêu cầu)" → Google đã có phòng vệ chủ động; càng dùng nhiều càng bị thử thách nhiều.
- Có tham số "Delay giữa job" và cảnh báo lỗi 403/409, kèm khuyến nghị "chạy nhiều tài khoản thì nên thêm proxy" → tức là đang chủ động tránh bị phát hiện, và bản thân tác giả cũng biết là rủi ro.
- App chưa ký chữ ký số, bị Windows Defender chặn/xoá, hướng dẫn user **tắt Smart App Control** để cài. Đây là rủi ro bảo mật thật cho người dùng cuối, độc lập với vấn đề ToS.

### 3.4. Kết luận kiến trúc

Cái "miễn phí" đó không miễn phí — nó đổi chi phí API thành: rủi ro mất tài khoản, bảo trì liên tục khi endpoint đổi, và không thể thương mại hoá đàng hoàng. Với dự án này (đã chốt hướng desktop app, có thể bán sau — xem CLAUDE.md), **đường fal.ai trả phí theo key hợp pháp là lựa chọn đúng**, kể cả khi đắt hơn: chi phí dự đoán được, không mất tài khoản, bán được mà không lo pháp lý.

Phần thật sự đáng học từ GOHA không phải cơ chế cookie, mà là những thứ ở Phần 1-2 và trong [ai-video-generation/research.md](../ai-video-generation/research.md) Phần 6: thiết kế MCP cho agent điều khiển, scope-based token, pluggable model directory, pipeline làm sạch giọng mẫu, và cách phơi tham số concurrency ra cho người dùng.

## Việc cần quyết định nếu làm tiếp

Đã chốt (xem mục QUYẾT ĐỊNH đầu tài liệu): ~~TTS local~~, ~~voice cloning offline~~ — bỏ, vì không đủ GPU/VRAM.

Còn lại:

- [ ] **Gemini TTS free tier**: có đáng thêm vào `adapters/tts/` không? Điểm hấp dẫn duy nhất so với Edge-TTS đang có là **style prompt** (điều khiển tông giọng/cảm xúc bằng câu mô tả) + 30 giọng. Đánh đổi: cần key, quota free thấp, và quota tính theo project nên không pool được. Nếu Edge-TTS đang đủ dùng thì bỏ qua.
- [ ] **Từ điển phát âm** (xem ai-video-generation/research.md Phần 6.3): bảng thay thế do user tự thêm (vd "CapCut" → "cáp cắt") áp dụng trước khi gửi sang TTS. **Không cần GPU, không cần model — chỉ là string replacement + 1 bảng DB.** Rẻ nhất và giá trị rõ trong nhóm ý tưởng TTS, áp dụng được cho cả Edge-TTS lẫn ElevenLabs. Đây là thứ đáng làm nhất còn sót lại.
- [ ] **Inpainting xoá watermark**: có cần nâng từ "che vùng mờ" (Phase 13 đã có) lên `cv2.inpaint` không? cv2 Inpaint **không cần GPU** (khác LaMa) và OpenCV có thể đã nằm trong dependency — nên đây là nhánh local duy nhất còn khả thi sau khi bỏ TTS local. Cần đánh giá: chất lượng che mờ hiện tại đã đủ chưa.
- [ ] **CapCut TTS**: xác minh có API công khai hợp pháp không (xem cảnh báo Phần 1.1) — nếu không thì loại hẳn, đừng để lửng.
