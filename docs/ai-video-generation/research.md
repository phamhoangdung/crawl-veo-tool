# Research: Tạo video bằng AI generative (node-based) + mở rộng Account Pool

Ngày research: 2026-09-09. Nguồn gốc ý tưởng: Google Flow (Google Labs) — screenshot workflow node-based: nguồn media (ảnh nhân vật/cảnh mẫu) → Image Generator (Nano Banana 2) → Video Generator (Omni Flash/Veo) → ghép nhiều clip thành 1 video. Video tham khảo: https://www.youtube.com/watch?v=ZY4VYW_d1pY

**Đây là tài liệu research (chưa phải plan/phase thực thi)** — mục đích: hiểu bối cảnh kỹ thuật, đánh giá độ khả thi, liệt kê rủi ro/quyết định cần chốt trước khi viết `docs/phases/phase-14-*.md` (nếu quyết định làm).

## Tại sao việc này khác với những gì tool đang làm

Toàn bộ pipeline hiện tại (Phase 1-13) là **re-up**: crawl video có sẵn từ Bilibili/Douyin → dịch/lồng tiếng → xuất. Phase 10 (video kể chuyện) ghép TTS với **video nền có sẵn do người dùng tự upload** — cố ý loại "tự sinh video nền bằng AI" ra khỏi phạm vi (xem phase-10, mục Phạm vi).

Ý tưởng lần này là một trục hoàn toàn khác: **tạo video mới từ đầu bằng generative model** (ảnh nhân vật/cảnh mẫu → ảnh sinh ra bởi AI → video sinh ra bởi AI), không dựa trên nội dung có sẵn nào. Đây gần với cách Google Flow, Kling AI Studio, Runway hoạt động: một **node-based visual builder** nơi mỗi bước (sinh ảnh, sinh video, ghép cảnh) là 1 node có thể chain lại.

## Phần 1: Google Flow hoạt động thế nào (từ ảnh + research)

Từ ảnh chụp bạn gửi và tài liệu công khai về Google Flow (Google Labs, ra mắt I/O 2025, hợp nhất Flow+Whisk+ImageFX thành 1 giao diện từ 2026-02-25):

- **Nguồn media**: người dùng upload sẵn các bộ ảnh tham chiếu (character sheet nhân vật ở nhiều góc, ảnh cảnh nền) — đúng như 3 khối "NGUỒN MEDIA" bên trái ảnh bạn gửi.
- **Node "Image Generator"**: nhận nguồn media + prompt text, chọn model (vd "Nano Banana 2" — tên lóng của Gemini image model), tỉ lệ khung hình, độ phân giải → sinh ra 1 ảnh keyframe mới (giữ đặc điểm nhân vật/cảnh từ ảnh tham chiếu, đổi bối cảnh/hành động theo prompt).
- **Node "Video Generator"**: nhận ảnh keyframe làm frame đầu (hoặc frame đầu+cuối để nội suy chuyển cảnh), chọn model video (Veo 3.1 các tier, ở đây gọi "Omni Flash"), duration (4s/8s...), tuỳ chọn voice-over → sinh video ngắn.
- **Chain nhiều node** song song (2 nhánh trong ảnh: "SUNDAY" và "MONDAY" — 2 cảnh khác nhau trong cùng 1 kịch bản/tập), rồi ghép nối các clip 4-8s lại thành video hoàn chỉnh dài hơn.
- **"Chạy nguồn" / "Chạy đồng thời" / số lượng (2)**: hàng loạt hoá — chạy nhiều biến thể cùng lúc rồi chọn kết quả tốt nhất (đây chính là điểm chạm với "account pool": chạy đồng thời nhiều job cần nhiều quota cùng lúc).
- Prefix "EP-001" + panel "Tài nguyên (242)" bên phải: quản lý output theo tập/episode, thư viện asset đã sinh ra được đánh số và tái sử dụng.

**Bản chất kỹ thuật**: đây không phải 1 API gọi 1 lần ra video hoàn chỉnh, mà là **pipeline nhiều bước ngắn** (mỗi video generator call chỉ ra 4-8s) + kỹ thuật giữ tính nhất quán nhân vật/cảnh qua nhiều lần gọi độc lập (xem Phần 3) + hậu kỳ ghép nối. Google Flow là lớp UI/orchestration phía trên các model (Nano Banana/Gemini image, Veo), không phải bản thân model.

## Phần 2: Các provider tạo video AI khả dụng qua API (2026)

| Provider | Model | Giá ước tính (per giây, có audio) | Ghi chú |
|---|---|---|---|
| Google (Gemini API / Vertex AI) | Veo 3.1 | $0.40/s (1080p) – $0.60/s (4K); bản Lite/no-audio rẻ hơn ($0.03-0.20/s) | Audio đồng bộ lời thoại/môi sinh ra cùng lúc; hỗ trợ image-to-video, frame-to-frame (start+end keyframe), scene extension (chain tới 20 clip ra video 140s+), 4K upscale |
| Kuaishou | Kling 3.0 | ~$0.10/s (60s ≈ $4.50); Turbo cao hơn (~$0.11/s) | Rẻ nhất trong nhóm chất lượng cao; có "Character Reference" giữ khuôn mặt/tỉ lệ cơ thể xuyên nhiều cảnh |
| Runway | Gen-4.5 | ~$0.12/s (10s ≈ $1.20, 60s ≈ $7.20) | Đắt nhất, mạnh về camera control |
| Luma | Ray 2 / Ray 3 | Ray 2: ~$0.04/s; Ray 3: $3-9 cho 6 clip 5s | Rẻ, phù hợp thử nghiệm |

**Truy cập gián tiếp qua aggregator** (fal.ai, Replicate, kie.ai): 1 API key duy nhất gọi được nhiều model (Veo, Kling, Seedance, Hailuo...), đổi model chỉ cần đổi 1 tham số. Đánh đổi: cộng thêm phụ phí per-call, phụ thuộc uptime của bên thứ 3, nhưng tiết kiệm công sức tích hợp N adapter riêng lẻ — **đúng tinh thần đa nhà cung cấp đã chốt trong CLAUDE.md** (OpenAI, Google, ElevenLabs, Azure... chọn theo tác vụ), có thể coi fal.ai là 1 "provider" nữa trong danh sách thay vì bắt buộc tích hợp trực tiếp từng hãng.

## Phần 3: Kỹ thuật giữ nhân vật/cảnh nhất quán qua nhiều clip

Vì mỗi lần gọi video-gen là 1 lần sinh độc lập (model không "nhớ" giữa các lần gọi), để nhiều clip trông như cùng 1 nhân vật/bối cảnh cần:

1. **Character sheet chuẩn bị trước**: ảnh nhân vật ở nhiều góc (trước/nghiêng/sau) + cận mặt — dùng làm ảnh tham chiếu cố định, đính kèm vào MỌI prompt sinh ảnh/video sau này thay vì mô tả lại bằng text mỗi lần (giảm trôi đặc điểm — "identity drift").
2. **Reference-to-video tốt hơn start-frame-only**: nếu chỉ đưa 1 ảnh làm frame-đầu, nhân vật có thể trôi dạng dần theo thời lượng clip; đưa ảnh làm "reference" xuyên suốt (Kling Character Reference, hoặc theo cách Flow dùng lại node ảnh đã sinh) giữ nhất quán tốt hơn.
2. **Sinh ảnh trước bằng Image Generator, rồi mới Video Generator từ đúng ảnh đó** — đúng pattern trong ảnh Google Flow: ảnh giữ vai trò "khoá" đặc điểm trước khi thổi hồn chuyển động, tránh việc video-gen tự diễn giải lại nhân vật từ text.
3. **Frame-to-frame (start+end keyframe)**: sinh 2 ảnh keyframe (đầu cảnh + cuối cảnh) bằng Image Generator, sau đó Video Generator nội suy chuyển động giữa 2 frame — kiểm soát tốt hơn để mỗi clip "khớp" clip trước về vị trí/tư thế nhân vật.

## Phần 4: Account Pool áp dụng cho video-gen — có vấn đề

Đây là phát hiện quan trọng nhất, khác với giả định ban đầu trong ảnh/câu hỏi của bạn:

> **Rate limit của Gemini API (bao gồm Veo) áp dụng theo *project*, không theo *API key*.** Nhiều key trong cùng 1 project chia sẻ chung 1 quota pool — tạo thêm key không tăng quota. Đây là khác biệt căn bản so với OpenAI/ElevenLabs (nơi mỗi key = 1 tài khoản = 1 quota riêng, đúng như cơ chế `pick_key_for_task` round-robin đã build ở Phase 8).

Hệ quả cho việc mở rộng Account Pool (Phase 8) sang video-gen:

- **Với OpenAI-style key (Kling, Runway, Luma, fal.ai, ElevenLabs...)**: cơ chế hiện có ở `api_key_service.py` (pick theo LRU, cooldown khi 429, reactivate) áp dụng được ngay, không cần đổi kiến trúc — chỉ cần thêm `provider_errors.py` nhận diện 429 của từng hãng + adapter gọi API tương ứng.
- **Với Google Veo qua Gemini API**: phải pool theo **project** (mỗi project GCP riêng, có billing riêng), không phải theo key lẻ — nghĩa là "nhiều account" ở đây = nhiều **Google Cloud project** (mỗi project 1 service account/API key gắn với billing account khác nhau), không phải nhiều key rời trong cùng 1 project như đang làm với OpenAI. Cần bổ sung khái niệm mới trong model `ApiKey` (hoặc field `pool_group`/`project_id`) để phân biệt "key độc lập" (OpenAI-style) với "key thuộc cùng project, KHÔNG độc lập quota" (Google-style) — nếu không phân biệt, hệ thống sẽ tưởng nhầm đã pool được quota trong khi thực ra vẫn dùng chung 1 giới hạn.
- **Google Vertex AI (thay vì Gemini API)** là lựa chọn khác cho Veo — quota theo GCP project + region, cấu hình linh hoạt hơn nhưng phức tạp hơn (cần service account, billing account riêng biệt thật sự để có quota độc lập thật).

## Phần 5: Ảnh hưởng tới kiến trúc hiện tại nếu làm

**Không thay chi phí ProcessPoolExecutor/Celery đã có** — sinh ảnh/video là I/O-bound (chờ API trả về), không cần đổi executor.

Các điểm cần quyết định trước khi viết phase mới:

1. **Vị trí trong roadmap**: đây là mở rộng của Phase 10 (bỏ giới hạn "ngoài phạm vi: tự sinh video nền") hay 1 phase hoàn toàn mới (Phase 14)? Về mặt data model, nó cần `background_video` được sinh ra thay vì upload — có thể tái dùng `background_library_service` (lưu kết quả sinh ra như 1 "video nền" bth) thay vì viết service riêng.
2. **Chi phí thật sự cao và biến động theo model** — khác hẳn dịch/TTS (rẻ, ổn định). 1 video kể chuyện 60s ghép từ clip 8s cần ~8 lần gọi video-gen; ở Veo 3.1 1080p+audio (~$0.40/s) là ~$19; ở Kling 3.0 (~$0.10/s) là ~$4.8. Cần UI ước tính chi phí trước khi chạy (đã có tiền lệ ở Phase 3 "cost estimate") và cảnh báo rõ ràng — rủi ro đốt tiền nếu chạy hàng loạt qua n8n mà không kiểm soát.
3. **Node-based UI là đầu tư frontend lớn** — Google Flow dùng canvas kéo-thả (giống React Flow/xyflow). Đây là 1 loại UI khác hẳn form-based hiện có của tool (Crawl, API Keys, Editor timeline ở Phase 13). Cần đánh giá: có cần full node-canvas như Flow, hay 1 phiên bản đơn giản hoá (form tuần tự: chọn ảnh tham chiếu → sinh ảnh → duyệt → sinh video → ghép) đã đủ dùng cho nhu cầu cá nhân? Timeline editor ở Phase 13 đã có sẵn phần "kéo-thả sắp xếp clip" — có thể tái dùng cho bước ghép cuối, không cần dựng lại.
4. **Account Pool schema cần thêm khái niệm "pool group"** để xử lý đúng trường hợp Google (theo Phần 4) — nếu không, tính năng "thêm nhiều key Google để tăng quota" sẽ không hoạt động như kỳ vọng và cần cảnh báo rõ cho người dùng ngay trên UI thay vì để họ tự khám phá ra sau khi vẫn bị 429.
5. **Compliance/bản quyền**: khác với re-up (rủi ro bản quyền nội dung crawl) và video kể chuyện (rủi ro templated/inauthentic content, đã phân tích ở `docs/scale-reup-features/plan.md`), nội dung 100% AI-generated có rủi ro riêng: 1 số nền tảng (YouTube) yêu cầu gắn nhãn "made with AI" (đã bắt buộc từ 2024), cần rà lại chính sách hiện hành trước khi thêm vào pipeline xuất bản.

## Việc cần quyết định trước khi viết phase thực thi

- [ ] Làm tiếp trong Phase 10 (story videos) hay tách Phase 14 riêng?
- [ ] Provider nào làm trước: gọi trực tiếp Veo (Gemini API) hay qua aggregator (fal.ai) để có nhiều model qua 1 tích hợp?
- [ ] Mức độ UI: node-canvas đầy đủ (như Flow) hay pipeline tuần tự đơn giản hoá?
- [ ] Có cần thêm khái niệm "pool group"/"project" vào `ApiKey` model để pool đúng cho Google, hay tạm thời chỉ hỗ trợ pool đúng nghĩa cho các provider kiểu OpenAI (Kling/Runway/Luma/fal.ai) và ghi chú rõ Google không pool được qua nhiều key?
- [ ] Ngân sách/ngưỡng cảnh báo chi phí trước khi chạy hàng loạt.

## Phần 6: Học từ GOHA Flow Studio (case study thực tế, 2026-09-09, cập nhật có ảnh chụp màn hình)

Kênh YouTube "Nông Dân Học AI" (@NongDanAI99) giới thiệu 1 tool thương mại tên **GOHA Flow Studio** — desktop app (Windows, Electron/Tauri-style) + Chrome extension, bán subscription, mục đích tương tự Google Flow nhưng tự động hoá đa tài khoản. Nguồn: transcript 2 video + 21 khung hình trích trực tiếp từ video tại các mốc thời gian cụ thể, lưu tại `docs/ai-video-generation/goha-screenshots/` (đặt tên theo `<video>-<số>-<mô tả>.jpg`, xem để đối chiếu bố cục UI thật khi thiết kế). 2 ảnh đã xoá vì lộ thông tin tài khoản/dịch vụ bên thứ 3 không liên quan đến kỹ thuật GOHA.

### 6.1. Cú pháp bám dính ảnh tham chiếu vào đúng prompt

Quan sát trực tiếp từ ảnh `install-01`, `install-05`, `install-07` (không phải cú pháp `a+a` như suy đoán ban đầu từ transcript — thực tế dùng cú pháp **mention `@ten_ref`**):

- Mỗi ảnh/thư mục tham chiếu được đặt 1 tên định danh khi upload, ví dụ `char_sunhui_hero`, `char_sunhui_sheet`, `prop_tongjang`.
- Trong ô prompt (dù nhập tay hay batch), user chèn thẳng `@char_sunhui_hero @char_sunhui_sheet @prop_tongjang` ở đầu câu prompt, sau đó là mô tả cảnh bằng tiếng Anh (`Over-the-shoulder medium shot, 50mm, the counter clerk over her shoulder...`).
- Tool parse các token `@ten` trong text prompt, tự động đính kèm đúng ảnh tương ứng khi gọi API sinh ảnh/video — không cần thao tác chọn ảnh thủ công qua UI kéo-thả.
- UI hiển thị kết quả matching ngay trong bảng batch: mỗi hàng có 2-3 avatar thumbnail nhỏ (ảnh ref đã match) đứng trước cột text prompt, để user xác nhận bằng mắt trước khi chạy.
- Sidebar trái có "THƯ VIỆN REF" — danh sách các thư mục ref đã tạo (tích chọn để đưa vào "Ảnh ref đang dùng"), và ô "Ảnh ref đang dùng (12)" hiển thị dạng grid thumbnail nhỏ — đây là tập ảnh khả dụng để prompt có thể `@mention` tới.

**Áp dụng cho Phase 14**: `character_reference_service` nên cho phép đặt `name` là 1 slug ngắn (không dấu, không khoảng trắng — dùng làm mention token), và tầng prompt-parsing (dù ở form tuần tự hiện tại chỉ cần match 1 bộ ref/lần, không cần parse hàng loạt) vẫn nên áp dụng quy ước `@name` để nếu sau này mở rộng sang batch, không phải đổi cú pháp đã quen dùng. Vì Phase 14 chọn form tuần tự đơn-item (không batch), tính năng parse `@mention` hàng loạt chưa cấp thiết — nhưng đặt tên ref theo slug ngay từ đầu là rẻ và tương thích ngược.

### 6.2. MCP server để agent điều khiển toàn quyền pipeline — thiết kế chi tiết quan sát được

Ảnh `install-10` và `tts-03` (2 phiên bản, `tts-03` mới hơn) cho thấy màn "Agent API · điều khiển bằng AI Agent" trong tab Cài đặt:

**Scope-based API key** (không phải toàn quyền nhị phân on/off) — checkbox riêng từng scope khi tạo key:
`assets:read`, `assets:write`, `config:read`, `gen:write`, `jobs:read`, `jobs:write`, `keys:read`, `models:read`, `session:write`, `tools:write`, `voice:clone`, `voice:read`, `voice:write` — đặt tên theo mẫu `<module>:<action>`. Nút "Full quyền" tick tất cả 1 lần cho tiện, nhưng mặc định là chọn từng scope.

**Vòng đời key**:
- Đặt tên gợi nhớ khi tạo (vd `claude-code`), bấm "Tạo key" → hiện plaintext dạng `sk_local_...` **chỉ 1 lần** (banner cảnh báo rõ "Key chỉ hiện 1 lần — copy & lưu ngay"), sau đó chỉ hiện dạng ẩn (mask) trong danh sách.
- Danh sách các key/session đã tạo hiển thị dạng log phía dưới: tên, ID ngắn (8 ký tự hex), scope đã cấp (rút gọn: `assetsread · assetswrite · configwrite · genwrite · jobsread · jobswrite`), và timestamp tạo — cho phép audit lại đã cấp quyền gì cho ai, có nút xoá riêng từng key.
- Quan sát thấy nhiều session tên `chrome-sidepanel` với scope hẹp hơn (`jobs:read · jobs:write · assets:read · assets:write · models:read`) — tức là **extension trình duyệt cũng tự tạo 1 session key riêng, scope hẹp hơn agent chính** (không có `voice:*`, `config:*`), theo nguyên tắc least-privilege giữa các "client" khác nhau của cùng hệ thống.

**Endpoint & MCP config mẫu** hiển thị sẵn để copy:
- REST base URL: `http://127.0.0.1:48322/api/v1` (server local, cổng cố định).
- Khối JSON mẫu cho `mcpServers` (tương thích Claude Desktop/Claude Code/Codex/Antigravity):
  ```json
  {
    "mcpServers": {
      "goha": {
        "command": "D:\\GOHA VEO TOOL\\.venv\\Scripts\\python.exe",
        "args": ["-m", "goha", "mcp"],
        "env": {
          "GOHA_API_KEY": "sk_local_...",
          "GOHA_API_BASE": "http://127.0.0.1:48322/api/v1",
          "PYTHONUTF8": "1",
          "PYTHONPATH": "D:\\GOHA VEO TOOL"
        }
      }
    }
  }
  ```
  → xác nhận: MCP server không phải 1 process độc lập luôn chạy nền, mà **khởi động theo yêu cầu bởi chính agent** (Claude Code spawn subprocess `python -m goha mcp` khi cần), giao tiếp qua stdio — đúng chuẩn MCP local server (không phải remote/SSE). Server con này chỉ là 1 lớp mỏng gọi vào REST API cục bộ (`GOHA_API_BASE`) đã chạy sẵn (desktop app tự chạy 1 FastAPI/uvicorn nội bộ), nghĩa là kiến trúc thực chất là **MCP-over-stdio wrapper quanh 1 REST API local** — không phải MCP server tự chứa toàn bộ logic.
- Có link tài liệu riêng "docs/agent-api.md" đi kèm app — gợi ý nên viết tài liệu tương tự (README riêng cho MCP tool) khi làm.

**Áp dụng cho Phase 14** — thiết kế cụ thể hơn bản trước:

| Thiết kế | Quyết định cho Phase 14 |
|---|---|
| Kiến trúc MCP | MCP server chạy qua stdio, **do agent tự spawn** (không phải service nền riêng) — dùng `mcp` Python SDK chính thức, `command` trỏ tới venv backend đã có, chạy `python -m app.mcp_server` (hoặc tương tự), đọc `GOHA_API_KEY`-tương-đương từ biến môi trường, gọi vào chính FastAPI app đang chạy ở `:8000` qua HTTP nội bộ — tái dùng đúng service layer, không viết lại logic. |
| Scope | Áp dụng scope hẹp hơn GOHA (vì Phase 14 chỉ cần sinh nội dung): `assets:read`, `assets:write` (character reference CRUD), `gen:write` (generate keyframe/video), `jobs:read` (theo dõi trạng thái generate), `cost:read` (đọc cost-estimate). **Không** có `keys:*`/`config:*`/`session:*` — không cho MCP đụng vào quản lý API key provider hay cấu hình hệ thống, đúng nguyên tắc đã chốt trước đó (không expose thanh toán/quản lý tài khoản). |
| Vòng đời key | Tạo key riêng cho mục đích MCP (không dùng chung JWT session của web UI) — hiện plaintext 1 lần, lưu hash trong DB, cho phép thu hồi (revoke) qua UI/API riêng. Tái dùng pattern hash+lookup đã có nếu `api_key_service.py` (Phase 8) đã có cơ chế tương tự cho key nội bộ; nếu chưa có, model mới nhỏ `McpAccessToken` (`name`, `token_hash`, `scopes: list[str]`, `created_at`, `revoked_at`). |
| Audit | Log lại mỗi lần MCP tool được gọi (tool name, args rút gọn, timestamp, token id) vào bảng nhỏ hoặc file log — không cần UI riêng ở Phase 14, nhưng để sẵn cho việc debug khi agent chạy tự động qua đêm. |

Danh sách MCP tool cụ thể đề xuất (map 1-1 vào endpoint đã liệt kê trong phase-14):

| MCP tool | Input | Output | Endpoint REST tương ứng |
|---|---|---|---|
| `list_character_references` | (không) | danh sách `{id, name, description, thumbnail_url}` | `GET /character-references` |
| `create_character_reference` | `name (slug)`, `description`, `file_paths[]` | `{id, name}` | `POST /character-references` |
| `estimate_generation_cost` | `type (image\|video)`, `model`, `duration?` | `{estimated_cost_usd, currency}` | `GET /generate/cost-estimate` |
| `generate_keyframe` | `character_ref_id`, `prompt`, `model` | `{asset_id, file_url, cost_actual_usd}` | `POST /generate/keyframe` |
| `generate_video_clip` | `keyframe_asset_id`, `prompt`, `model`, `duration` | `{asset_id, file_url, cost_actual_usd}` | `POST /generate/video-clip` |
| `get_generation_job` | `asset_id` | `{status, error?, file_url?}` | `GET /generate/{asset_id}` (nếu generate là async — cần xác nhận khi code) |

Mỗi tool là 1 hàm Python decorator `@mcp.tool()` gọi thẳng service tương ứng, trả JSON — không thêm logic nghiệp vụ mới trong lớp MCP.

### 6.3. Ý tưởng cho Phase 2-4 (TTS) — chỉ ghi chú, chưa lên kế hoạch

GOHA gom toàn bộ TTS vào 1 tab "TTS Studio" với **12 sub-tab** (ảnh `tts-04`, `tts-09`, `tts-10`): Tạo giọng nhanh · Đổi giọng AICONG · Hội thoại · Lồng tiếng video · Voice Styles · Đọc truyện · Bản tin · Clone VieNeu · Clone OmniVoice · Làm sạch giọng mẫu · Phụ đề & Lồng tiếng · Điều khoản & Trách nhiệm. Header ghi rõ 4 công cụ nền: Flow (theo tài khoản, 30 giọng Gemini) · VieNeu (máy bản, miễn phí, CPU/GPU) · Gemini API (key riêng) · CapCut (miễn phí, 113 giọng).

3 tính năng đáng chú ý cho pipeline lồng tiếng hiện có của dự án (Phase 2-4, **không** phải Phase 14):

- **Voice cloning từ mẫu ghi âm** (ảnh `tts-06`): upload video/audio bất kỳ → UI **waveform kéo 2 thanh chọn đoạn** giọng rõ nhất (hướng dẫn ngay trên UI: "vùng sáng = giữ, 2 rìa tối = bỏ", có nút "Bỏ chọn (tự tìm đoạn)" để tool tự chọn) → dropdown "Độ dài đoạn mẫu" (20 giây khuyến nghị) → dropdown "Chuẩn hoá" (Chuẩn clone khuyến nghị) → checkbox "Cân bằng âm lượng (chuẩn YouTube)" → nút "Làm sạch" → khung "Nghe & So sánh" (A/B gốc vs đã làm sạch). Pipeline ngầm: tách nhạc → khử ồn → chọn đoạn → ra mẫu sạch (chạy GPU máy người dùng). Cảnh báo trên UI: "Mẫu clone chỉ nên chuẩn hoá *nhẹ* — làm dày/EQ mạnh khiến giọng nhân bản bị giả".
- **Thiết kế giọng không cần mẫu** (ảnh `tts-09`): thay vì clone, cho chọn Giới tính / Độ tuổi / Cao độ qua dropdown ("— mặc định —" = tự nhiên) để tổng hợp giọng ảo. Model TTS pluggable: "thả model hợp lệ vào `models/` → hiện ở đây" (mặc định `KhanhTTS-OmniVoice`) — pattern hay: cho phép thêm model local mà không cần sửa code.
- **Voice Styles bằng ngôn ngữ tự nhiên + LLM** (ảnh `tts-04`): textarea mô tả giọng muốn có (placeholder ví dụ: "Giọng nữ trẻ khoảng 20 tuổi, trong trẻo tươi sáng, nói nhanh vừa, dùng để đọc quảng cáo mỹ phẩm vui nhộn trên TikTok"), 4 nút gợi ý nhanh (Thuyết minh / Quảng cáo / Truyện ma / Cho bé), nút "Gợi ý phong cách" → gọi LLM → sinh ra system-prompt chi tiết + **đề xuất luôn voice ID cụ thể** trong danh sách Gemini (vd Leda, Orus). UI ghi rõ điều kiện: cần API key LLM ở mục Cài đặt · 05 · LLM, và gợi ý user nên nêu gì để kết quả chuẩn (giới tính/tuổi, vùng miền, chất giọng, cảm xúc, tốc độ, mục đích).
- **Từ điển phát âm** (transcript, chưa capture được ảnh): bảng thay thế cách đọc do user tự thêm (vd viết "CapCut" → đọc "cáp cắt", "video" → "vi đê ô") — áp dụng tự động trước khi gửi sang TTS, giải quyết vấn đề model đọc sai từ nước ngoài. Đây là tính năng nhỏ nhưng giá trị cao và rẻ để làm.

Rủi ro pháp lý: clone giọng người khác không xin phép là vi phạm quyền nhân thân/bản quyền — GOHA có hẳn 1 tab "Điều khoản & Trách nhiệm" và người làm video cũng cảnh báo rõ (nêu ví dụ clone giọng nghệ sĩ nổi tiếng là vi phạm dù ít bị kiện). Nếu dự án làm tính năng này, **phải** có cảnh báo tương đương trong UI, và không nên ship sẵn thư viện giọng clone của người thật (GOHA cố ý không ship danh sách giọng clone sẵn vì lý do pháp lý).

Không đưa vào Phase 14 vì thuộc phạm vi lồng tiếng đã có sẵn service riêng (Phase 2-4) — nếu muốn làm, nên mở lại `docs/phases/phase-4-audio-quality.md` hoặc tạo ghi chú follow-up riêng khi có nhu cầu cụ thể, tránh trộn 2 pipeline (re-up lồng tiếng vs AI-gen video) vào chung 1 phase.

### 6.4. Các phát hiện kỹ thuật khác từ ảnh chụp (đáng tham khảo)

**Engine xoá watermark — 4 lựa chọn có đánh đổi rõ ràng** (ảnh `install-02`, dropdown "Engine xoá watermark"):

| Engine | Đặc điểm (nguyên văn nhãn trên UI) |
|---|---|
| Delogo (ffmpeg) | nhanh, làm mờ nền |
| Reverse Blend | nhanh, giữ chi tiết |
| cv2 Inpaint | đẹp, không cần GPU |
| LaMa AI | đẹp/kỹ nhất, chậm (GPU) |

Đáng giá cho dự án: Phase 13 đã có tính năng "che logo/phụ đề gốc bằng vùng mờ" (xem commit `6d7ae92`) — tương đương mức Delogo. Nếu sau này muốn nâng chất lượng, thứ tự đầu tư hợp lý là cv2 Inpaint (không cần GPU, đã có OpenCV trong hệ sinh thái Python) trước khi nghĩ tới LaMa (cần GPU + model nặng).

**Cấu hình concurrency phơi ra cho người dùng** (ảnh `install-02`, `install-03`): "Luồng / Cookie" (mặc định 2, có nút Auto — "luồng song song"), "Luồng / account" (mặc định 3 — "worker mỗi account"), "Delay giữa job" (mặc định 5 giây). Tức là song song 2 chiều: nhiều account × nhiều worker/account, cộng delay để giảm rate-limit. Dự án hiện dùng ProcessPoolExecutor với concurrency cố định — nếu Phase 14 chạy nhiều job generate song song, cân nhắc phơi 1-2 tham số tương tự (số job đồng thời, delay) ra UI thay vì hardcode, vì ngưỡng an toàn phụ thuộc provider và thay đổi theo thời gian.

**Đặt tên output theo dự án/tập** (ảnh `install-03`): ô "Tên output (prefix)" với placeholder `vd EP001 → EP001_001.png` — tự động đánh số tăng dần theo prefix user nhập. Khớp với nhu cầu quản lý theo tập/episode đã nêu ở Phần 1. Rẻ để làm, nên có ngay trong Phase 14 khi lưu `GeneratedAsset` (thêm field `output_prefix`/`sequence_no`, hoặc chỉ cần đặt tên file theo pattern này).

**Sinh video theo cặp start→end frame, nhiều kết quả/job** (ảnh `install-07`, tab "Tạo Video · Veo 3.1"): bảng batch có cột "START → END" (2 thumbnail: ảnh đầu + ảnh cuối, có nút "+ Thêm" để bổ sung), cột PROMPT, cột TIẾN ĐỘ, và cột "VIDEO KẾT QUẢ" chứa **4 slot Vid 1/2/3/4** — tức mỗi job sinh nhiều biến thể để user chọn. Xác nhận thiết kế frame-to-frame ở Phần 3 là đúng thực tế triển khai. Với Phase 14: nên cho `generate_video_clip` nhận `keyframe_start_asset_id` + `keyframe_end_asset_id?` (optional) ngay từ đầu thay vì chỉ 1 keyframe, vì đổi signature sau sẽ đụng cả MCP tool và UI.

**LLM sửa prompt bị chặn — hỗ trợ 5 provider** (ảnh `install-09`, mục "05 · LLM · sửa prompt vi phạm", mô tả: "Viết lại prompt bị Google chặn (giữ ý đồ, tuân chính sách)"): dropdown gemini / openai / claude / deepseek / openrouter + ô API key riêng, và system instruction để trong file ngoài (`goha/policy_fix_system_prompt.md`) — tách prompt ra file thay vì hardcode, dễ sửa mà không rebuild app. Dự án đã có multi-provider LLM từ Phase 3, nên tính năng này chỉ là 1 service mỏng gọi lại provider sẵn có; pattern "system prompt để ở file riêng" đáng áp dụng.

**Trạng thái hệ thống hiện trên header** (ảnh `tts-04`, `tts-09`): CPU % · GPU % · RAM dùng/tổng · VRAM — vì các model local (VieNeu/OmniVoice) ngốn tài nguyên và người dùng cần biết trước khi chạy. Nếu dự án thêm model local (Demucs đã có ở Phase 4, TTS local nếu làm), hiển thị VRAM/RAM khả dụng là cảnh báo hữu ích hơn là để job chạy rồi chết giữa đường.

## Nguồn

- [Google Flow AI Filmmaking Tool — Official Veo Guide 2026](https://whiskailabs.net/google-flow-ai-filmmaking-tool-veo-guide-2026/)
- [Google Flow + Veo Guide 2026: What Google's AI Filmmaking Stack Actually Includes](https://aividpipeline.com/blog/google-flow-veo-3-1-guide-2026)
- [Veo 3.1 - API Pricing & Benchmarks | OpenRouter](https://openrouter.ai/google/veo-3.1)
- [Veo 3 API Pricing Comparison — Kie.ai](https://kie.ai/v3-api-pricing)
- [AI Video API Pricing in 2026 — Apiframe](https://apiframe.ai/blog/ai-video-api-pricing-2026)
- [AI Video Generation API Pricing (July 2026) — buildmvpfast](https://www.buildmvpfast.com/api-costs/ai-video)
- [Kling vs Pika vs Luma: AI Video Model Comparison 2026](https://melies.co/kling-vs-pika-vs-luma)
- [The Ultimate Guide to Keeping Your Character Consistent in AI — Kling](https://kling.ai/blog/ai-character-consistency-guide)
- [Reference to Video AI — Keep Characters Consistent | Vidu AI](https://www.vidu.com/ai-reference-to-video)
- [Gemini API Rate limits | Google AI for Developers](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Are the Gemini API limits per project/account or per key? — Google AI Developers Forum](https://discuss.ai.google.dev/t/are-the-gemini-api-limits-per-project-account-or-per-key/92758)
- [fal.ai — AI Video Generation APIs for Developers](https://fal.ai/video)
- [AI Image & Video APIs 2026: FAL vs Replicate vs OpenAI — teamday.ai](https://www.teamday.ai/blog/ai-image-video-api-providers-comparison-2026)
