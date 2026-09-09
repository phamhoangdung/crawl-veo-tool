# Phase 14: Tạo video bằng AI generative (node-based đơn giản hoá)

Trạng thái: Chưa bắt đầu — phụ thuộc quyết định provider đầu tiên và nguyên liệu test (xem Nguyên liệu). Research nền tảng: [docs/ai-video-generation/research.md](../ai-video-generation/research.md).

## Mục tiêu
Luồng sản xuất mới, không dựa trên nội dung crawl hay video nền tự upload: ảnh nhân vật/cảnh mẫu → AI sinh ảnh keyframe (giữ đặc điểm nhân vật) → AI sinh video ngắn (4-8s) từ keyframe → ghép nhiều clip thành 1 video hoàn chỉnh. Lấy cảm hứng từ Google Flow nhưng đơn giản hoá thành pipeline tuần tự (không phải node-canvas kéo-thả).

## Phạm vi
**Trong phạm vi:** adapter provider sinh ảnh + sinh video mới (bắt đầu bằng fal.ai — 1 API key gọi được nhiều model: Veo, Kling, Luma...), quản lý bộ ảnh tham chiếu nhân vật/cảnh (character sheet) theo dự án, form tuần tự sinh ảnh keyframe → duyệt/chọn → sinh video từ keyframe đã chọn, lưu kết quả clip vào thư viện dùng chung với `background_library_service` (Phase 10) để tái dùng làm "video nền", cảnh báo chi phí trước khi chạy (tái dùng `cost_service` Phase 3), mở rộng Account Pool (Phase 8) để hỗ trợ provider kiểu OpenAI (mỗi key = 1 quota riêng: Kling/Luma/fal.ai) — **không** làm pool cho Google Veo trực tiếp ở phase này (xem Ngoài phạm vi). Thêm **MCP server** bọc quanh các endpoint character-reference + generate đã có, để agent ngoài (Claude Code/Codex) gọi trực tiếp thay vì qua UI — học từ case study GOHA Flow Studio (xem research Phần 6.2); chỉ expose thao tác sinh nội dung + đọc cost-estimate, không expose quản lý tài khoản/thanh toán. Thêm **chế độ fake adapter** (`FALAI_MODE=fake`) để phát triển không tốn phí, và **đường "ảnh tĩnh + Ken Burns"** làm lựa chọn thay cho sinh video ở những cảnh không cần chuyển động thật (xem mục Chiến lược giảm chi phí).

**Ngoài phạm vi:** node-canvas kéo-thả kiểu Google Flow (dùng form tuần tự đơn giản hơn), tích hợp trực tiếp Google Veo qua Gemini/Vertex API (vướng vấn đề quota theo *project* chứ không theo *key* — xem research mục Phần 4; để lại cho [Phase 15](phase-15-account-pool-groups.md) nếu sau này cần chất lượng Veo cụ thể), ghép/sắp xếp nhiều clip thành video dài (dùng **timeline editor Phase 13** có sẵn, không viết UI ghép riêng), gắn nhãn "made with AI" tự động lên metadata xuất bản (rà chính sách nền tảng thủ công trước, chưa tự động hoá), cú pháp bám dính ảnh tham chiếu hàng loạt kiểu `a+a` (chỉ cần khi có tính năng batch-generate, form tuần tự hiện tại là đơn-item — xem research Phần 6.1), tích hợp TTS đa nguồn/voice cloning vào studio này (thuộc Phase 2-4, xem research Phần 6.3).

## Chiến lược giảm chi phí (chốt 2026-09-09)

Sinh video là tác vụ đắt nhất toàn dự án (đắt hơn dịch/TTS hàng trăm lần), nên các quyết định dưới đây là **phần của thiết kế**, không phải tối ưu để sau. Mốc so sánh: 10 video 60s/tháng (mỗi video ghép từ ~8 clip 8s = 80 clip/tháng) tốn ~$256 nếu dùng Veo 3.1 + 4 biến thể/clip, xuống **~$18-25** khi áp các mục dưới.

| # | Quyết định | Ảnh hưởng | Ghi chú triển khai |
|---|---|---|---|
| 1 | **Ảnh tĩnh + Ken Burns thay cho sinh video** ở cảnh không cần chuyển động thật | Lớn nhất — sinh ảnh rẻ hơn sinh video ~50-100 lần | Cảnh tĩnh (người nói, cảnh nền) chỉ cần 1 ảnh + zoom/pan chậm bằng ffmpeg. Dùng `ffmpeg.py` đã có; ghép ở timeline editor (Phase 13). UI phải cho chọn "ảnh tĩnh + chuyển động camera" ngang hàng với "sinh video AI" ở bước ③ |
| 2 | **Chọn model theo từng cảnh**, không cấu hình toàn cục | Chênh ~10× giữa model rẻ nhất và Veo | Luma Ray 2 (~$0.04/s) cho cảnh nền/thử nghiệm; Kling 3.0 (~$0.10/s, Character Reference tốt) cho cảnh chính có nhân vật; Veo (~$0.40/s) chỉ khi cần audio đồng bộ khớp môi |
| 3 | **Video mặc định 1 biến thể** (ảnh thì 4) | Tiết kiệm 4× ở khâu đắt | GOHA mặc định 4 kết quả/job video = trả tiền gấp 4. Chỉ sinh thêm khi cái đầu không dùng được |
| 4 | **Cache/dedupe theo hash** `(prompt, ref_ids, model, duration)` | Chống đốt tiền do bấm lại | Nếu đã có trong `GeneratedAsset` → trả asset cũ + thông báo "dùng lại kết quả đã sinh, không tốn phí". Ngăn kịch bản refresh trang rồi bấm lại |
| 5 | **Duyệt ở khâu rẻ trước khâu đắt** | Phát hiện sai sớm | Luồng tuần tự (ảnh → chọn → video) đã có tác dụng này. Thêm: cho phép sinh video **4s để thử prompt chuyển động** trước khi làm 8s |
| 6 | **Hạn mức chi phí theo tháng**, không chỉ theo lần | Chặn thảm hoạ | Ngoài ngưỡng $1/lần đã có, thêm hạn mức tháng (đề xuất $30): chạm ngưỡng thì chặn, phải xác nhận mới tiếp. **Quan trọng nhất khi agent chạy tự động qua đêm qua MCP** — không ai ngồi xem |
| 7 | **LLM sửa prompt bị chặn policy** | Ngăn chuỗi thử-sai tốn kém | Prompt bị chặn vẫn có thể bị tính phí. LLM tính bằng cent, đã có multi-provider từ Phase 3 |

## Chế độ phát triển không tốn phí (`FALAI_MODE=fake`)

Dùng cho ~95% thời gian phát triển. Fake adapter cùng interface với adapter thật, trả file sinh sẵn bằng ffmpeg thay vì gọi API:

- Sinh video: `ffmpeg -f lavfi -i testsrc=duration=<n>:size=1280x720 -f lavfi -i sine=frequency=440 ...` → mp4 thật có video+audio, đúng thời lượng, `ffprobe` đọc được. Overlay `drawtext` ghi prompt + số cảnh để phân biệt clip khi ghép.
- Sinh ảnh: tương tự với 1 frame + text overlay.

**Phải mô phỏng cả hành vi xấu** — đây là phần không thể tái tạo bằng tiền thật theo ý muốn:

| Mô phỏng | Để test |
|---|---|
| Delay 30-60s | UI progress, "rời trang job vẫn chạy" |
| Random lỗi 429 | Rotation key trong pool (Phase 8) |
| Random lỗi policy-blocked | Luồng "LLM sửa prompt" |
| Lỗi quota hết | Banner cảnh báo, disable nút sinh |

Thang bậc test khi cần gọi API thật (toàn bộ Phase 14 nên tốn **dưới $2**):

| Mức | Cách | Chi phí | Dùng khi |
|---|---|---|---|
| 1 | Fake adapter | $0 | Toàn bộ UI, service, DB, timeline, MCP |
| 2 | 1 ảnh, model rẻ nhất | ~$0.01-0.04 | Xác nhận adapter thật đúng (auth, parse response) |
| 3 | Video 4s, Luma | ~$0.16 | Xác nhận luồng video thật end-to-end |
| 4 | Video 8s, model định dùng | ~$0.80 | Chỉ khi đánh giá chất lượng cuối |

Sinh ảnh còn có đường miễn phí thật: **Gemini API free tier** có quota ảnh/ngày, đủ để test bước sinh keyframe. Sinh video không có free tier đáng kể ở nhà nào.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
**Không cần nguyên liệu gì để BẮT ĐẦU** — nhờ `FALAI_MODE=fake`, phần lớn phase làm được mà chưa cần key hay credit. Các mục dưới chỉ cần trước khi verify thật (mức 2-4 ở thang bậc test).

- [ ] **API key fal.ai thật** — đăng ký tài khoản, lấy key. Credit dùng thử khi đăng ký là đủ cho mức 2-3; **không cần nạp thêm** nếu giữ kỷ luật fake adapter (cả phase ước tính dưới $2).
- [ ] **Ít nhất 1 bộ ảnh nhân vật mẫu** (2-4 góc: trước/nghiêng/cận mặt) để test tính nhất quán khi sinh keyframe — ảnh của bạn tự vẽ/chụp hoặc AI-generated đều được, miễn nhất quán 1 nhân vật.
- [x] **Model mặc định**: Kling 3.0 cho cảnh chính (rẻ, Character Reference tốt), Luma Ray 2 cho cảnh nền/thử nghiệm, Veo chỉ khi cần audio đồng bộ. Chốt theo mục Chiến lược giảm chi phí #2 — chọn theo từng cảnh, không cấu hình toàn cục. Tên model chính xác cần xác nhận lại tại thời điểm code (đổi nhanh theo thời gian).
- [x] **Ngưỡng chi phí**: giữ $1/lần gọi (pattern Phase 3) **và thêm hạn mức tháng $30** (mục Chiến lược #6) — quan trọng nhất khi agent chạy qua MCP.
- [x] Không làm Google Veo trực tiếp ở phase này — đã xác nhận, lý do ở research Phần 4 (quota theo project không theo key).
- [ ] **Quyết định nhỏ khi code**: Gemini API key (free tier) để test sinh ảnh miễn phí — có sẵn key Gemini từ phase trước không, hay bỏ qua và dùng luôn fake adapter?

## Việc cần làm

### Backend
- [ ] `app/adapters/falai/client.py` (mới): gọi fal.ai REST API — `generate_image(prompt, reference_images, model, aspect_ratio)`, `generate_video(prompt, keyframe_start, keyframe_end, model, duration)`. Nhận diện lỗi quota/rate-limit (429) thống nhất theo `provider_errors.py` đã có từ Phase 8. **`keyframe_end` optional ngay từ đầu** (frame-to-frame interpolation — GOHA/Google Flow đều dùng cặp start→end, đổi signature sau sẽ đụng cả MCP tool lẫn UI; xem research Phần 6.4).
- [x] `app/adapters/falai/fake.py` (mới): fake adapter cùng interface, dùng khi `FALAI_MODE=fake` (mặc định khi chưa có key) — sinh mp4/ảnh bằng ffmpeg `testsrc` + `sine` + `drawtext` (prompt + số cảnh). Mô phỏng delay 30-60s và random lỗi 429/policy-blocked/quota-hết (tỉ lệ cấu hình được qua env) — chi tiết ở mục "Chế độ phát triển không tốn phí". Chọn adapter ở một chỗ duy nhất (factory theo env), service không biết đang dùng fake hay thật.
- [x] `app/models/character_reference.py` (mới): bộ ảnh tham chiếu nhân vật/cảnh — `name` (**slug: không dấu, không khoảng trắng — dùng làm mention token `@name` trong prompt**, xem research Phần 6.1), `file_paths` (nhiều ảnh/góc), `description`, thuộc về 1 dự án/user.
- [x] `app/services/character_reference_service.py`: CRUD bộ ảnh tham chiếu (upload/list/xoá), validate `name` là slug hợp lệ + unique. Thêm `resolve_mentions()` parse `@ten` trong prompt.
- [x] `app/models/generated_asset.py` (mới): lưu kết quả sinh ra — `type` (`image`/`video`), `file_path`, `source_character_ref_id`, `prompt`, `provider`, `model`, `cost_estimate`, `output_prefix` + `sequence_no` (đặt tên file theo dự án/tập kiểu `EP001_001.png`, xem research Phần 6.4). Ảnh/video sinh ra lưu riêng bảng này, KHÔNG trộn với `Video` (khác state machine — không có `platform`/`source_url`).
- [x] `app/services/ai_generation_service.py`: `generate_keyframe(character_ref_id, prompt, model)` → gọi adapter, lưu `GeneratedAsset` type=image; `generate_video_clip(keyframe_start_asset_id, prompt, model, duration, keyframe_end_asset_id=None)` → gọi adapter, lưu `GeneratedAsset` type=video. Gọi `cost_service` ước tính trước khi submit, chặn nếu vượt ngưỡng đã chốt (trừ khi user xác nhận bỏ qua cảnh báo).
- [x] Cache/dedupe trong `ai_generation_service`: thêm field `request_hash` vào `GeneratedAsset` (hash của `prompt + ref_ids + model + duration`), kiểm tra trước khi gọi adapter — nếu trùng thì trả asset cũ kèm cờ `from_cache=True` để UI hiện "dùng lại kết quả đã sinh, không tốn phí" (Chiến lược #4). Cache tự bỏ qua nếu file đã bị dọn khỏi ổ đĩa.
- [x] `ffmpeg.py`: thêm `make_ken_burns_clip(image_path, output_path, duration, motion)` — sinh clip từ 1 ảnh tĩnh với zoom/pan chậm (`zoompan` filter), làm đường thay thế rẻ cho sinh video AI ở cảnh không cần chuyển động thật (Chiến lược #1 — đòn tiết kiệm lớn nhất). Kết quả lưu vào `GeneratedAsset` type=video, `provider="ffmpeg"`, `cost_estimate=0`. Hỗ trợ `zoom_in`/`zoom_out`/`pan_right`.
- [x] Hạn mức chi phí theo tháng trong `cost_service`: cộng dồn `cost_estimate` của `GeneratedAsset` theo tháng, chặn khi vượt hạn mức (mặc định $30, cấu hình được) — trả lỗi rõ ràng kèm số đã chi/hạn mức. Áp dụng cho **cả đường MCP** (agent chạy qua đêm là kịch bản dễ đốt tiền nhất, Chiến lược #6).
- [x] Đưa `GeneratedAsset` vào kho file dùng chung — **`background_library_service` (Phase 10) KHÔNG tồn tại** (Phase 10 chưa bắt đầu). Đích đúng là `asset_service` (Phase 9): đó mới là nguồn của `AssetPicker` trong Timeline Editor (`features/editor/asset-picker.tsx`). Thêm `export_to_asset_library()` gọi `asset_service.import_from_path()` — **copy** chứ không move, để bản gốc trong `storage/generated/` còn thì cache `request_hash` vẫn hiệu lực. Endpoint `POST /assets/{id}/export-to-library`.
- [x] `app/api/ai_generation.py`: gộp cả CRUD ảnh tham chiếu và generate vào 1 router `/api/ai-studio` (không tách `character_references.py` riêng — cùng 1 màn hình dùng, tách file chỉ thêm chỗ phải nhảy qua lại). 9 endpoint: `GET /mode`, `GET /budget`, `GET|POST /character-references`, `DELETE /character-references/{id}`, `GET /assets`, `GET /cost-estimate`, `POST /generate/keyframe`, `POST /generate/video-clip`, `POST /generate/ken-burns`. Map lỗi → HTTP: 409 vượt ngưỡng/lần, 402 vượt hạn mức tháng, 422 prompt bị chặn, 429 hết quota.
- [ ] Mở rộng `app/models/api_key.py`/`api_key_service.py` cho provider `falai` — dùng nguyên cơ chế pool theo key đã có (LRU, cooldown, reactivate), không cần đổi schema vì fal.ai là 1-key-1-quota giống OpenAI.
- [x] Test: `ai_generation_service` (16 test — mock adapter đếm số lần gọi để chứng minh cache KHÔNG gọi API, chặn ngưỡng/lần và hạn mức tháng, chi tiêu tháng trước không tính vào tháng này, đặt tên `EP001_001`), `character_reference_service` (12 test — CRUD, validate slug, dedupe `@mention` trùng). Ken Burns verify bằng ffmpeg+ffprobe thật (ngoài test suite, xem Ghi chú). **Còn thiếu**: rotation key `falai` trong pool (chưa có adapter thật nên chưa có gì để rotate).
- [x] `app/models/mcp_access_token.py` (mới): token cho agent ngoài — `name` (vd `claude-code`), `token_hash`, `scopes` (list), `created_at`, `revoked_at`. Plaintext dạng `sk_local_...` **chỉ hiện 1 lần lúc tạo**, sau đó chỉ lưu hash (pattern GOHA dùng, xem research Phần 6.2). Scope hẹp hơn GOHA, chỉ 5 loại: `assets:read`, `assets:write`, `gen:write`, `jobs:read`, `cost:read` — **không** có `keys:*`/`config:*` (MCP không được đụng API key provider hay cấu hình hệ thống).
- [x] `app/services/mcp_token_service.py` + `app/api/mcp_tokens.py`: tạo/list/revoke token, verify token+scope. Token lưu **hash SHA-256 một chiều** (khác API key provider dùng Fernet 2 chiều — token chỉ cần so sánh, không bao giờ đọc lại). `POST /api/mcp-tokens` trả kèm **khối config MCP sinh sẵn** (đường dẫn `sys.executable` thật + PYTHONPATH) để copy thẳng vào Claude Code.
- [x] `app/api/mcp_auth.py` (thêm ngoài kế hoạch — **cần thiết, nếu không scope chỉ là trang trí**): dependency `require_scope()` gắn vào từng endpoint. Web UI cục bộ không gửi token thì cho qua; có token thì BẮT BUỘC token hợp lệ + đúng scope (401 nếu token sai/đã thu hồi, 403 nếu thiếu scope).
- [x] `app/mcp_server.py` (mới): MCP server chạy **qua stdio, do agent tự spawn** (`python -m app.mcp_server`, không phải service nền riêng — xem research Phần 6.2), đọc token từ env, gọi REST API local. 7 tool: `list_character_references`, `estimate_generation_cost`, `generate_keyframe`, `generate_video_clip`, **`make_ken_burns_clip`** (thêm — để agent có đường miễn phí), `list_generated_assets`, `get_budget_status`. Mỗi tool chỉ gọi REST, không nhúng logic. **Không** có `create_character_reference` (upload multipart qua MCP không thực tế — agent không có file bytes; tạo ref làm qua UI).
- [x] Log audit: mỗi lần MCP tool được gọi đều có dòng log HTTP request (uvicorn) + log tạo token; **chưa** có bảng audit riêng (chưa cần ở phase này, log đủ để debug).
- [x] Test: 14 test cho `mcp_token_service` (hash không chứa plaintext, chặn scope lạ, token thu hồi bị từ chối, giữ record đã thu hồi để audit). Scope enforcement + MCP client thật verify bằng chạy live (xem Ghi chú), không mock.

### Frontend
- [x] Route mới `frontend/src/routes/_authenticated/ai-studio/index.tsx` + `frontend/src/features/ai-studio/index.tsx`: layout **sidebar cấu hình (trái) + vùng làm việc (phải)** theo 4 bước tuần tự — (1) chọn/tạo bộ ảnh tham chiếu nhân vật, (2) nhập prompt + chọn model ảnh → "Sinh ảnh" → xem lưới kết quả, chọn 1 ảnh ưng ý, (3) nhập prompt chuyển động + chọn model video + duration (+ tuỳ chọn ảnh cuối cho frame-to-frame) → "Sinh video" → xem preview, (4) nút "Thêm vào thư viện video nền" (gọi `background_library_service`) hoặc "Mở trong Timeline Editor" (Phase 13) để ghép nhiều clip. Wireframe chi tiết + luồng trạng thái: xem `docs/ai-video-generation/ui-ux-design.md`.
- [x] Bước ③ có **2 lựa chọn ngang hàng** (`components/video-step.tsx`): "Ảnh tĩnh + chuyển động camera" (miễn phí, ffmpeg Ken Burns — badge `Miễn phí`) và "Sinh video AI" (hiện giá theo model + thời lượng). **Ken Burns là mặc định**, kèm dòng giải thích khi nào cần video AI thật — Chiến lược #1.
- [x] Hiển thị ước tính chi phí trên nút "Sinh N ảnh"/"Sinh video" + badge ở header từng bước. Chọn model video **theo từng cảnh** ngay ở bước ③ (Luma/Kling/Veo kèm giá $/s), không phải cấu hình toàn cục — Chiến lược #2. Ảnh mặc định 4 biến thể, video luôn 1 — Chiến lược #3. Lỗi 409 (vượt ngưỡng/lần) mở Dialog "Vẫn tiếp tục" thay vì chặn cứng.
- [x] Toast "dùng lại kết quả đã sinh — không tốn phí" khi backend trả `from_cache=true`; khối "Đã tạo (N)" cuối trang có **Tổng: $X · N miễn phí**, badge "Tháng này: $X / $Y" ở header trang (đổi sang `destructive` khi hết hạn mức) — cảnh báo tự nhiên thay vì dialog.
- [x] Banner khi `FALAI_MODE=fake` + banner riêng khi đã hết hạn mức tháng (nhắc đường Ken Burns vẫn dùng được).
- [x] `frontend/src/lib/api.ts`: types + fetch helpers cho character reference, generated asset, generate endpoints, MCP token. Thêm `generatedAssetFileUrl()` + endpoint backend `GET /assets/{id}/file` (thiếu trong kế hoạch — không có nó thì browser không xem trước được ảnh/video).
- [x] Thêm "AI Studio" vào sidebar (`sidebar-data.ts`, nhóm Nội dung, icon `Sparkles`).
- [ ] Mở rộng trang `/api-keys`: thêm `falai` vào danh sách provider; thêm section quản lý **MCP access token** (tạo/copy-1-lần/revoke, tick scope) + khối JSON config MCP để copy sẵn. **Chưa làm** — API + client helper đã sẵn, chỉ còn phần UI.

## Tiêu chí hoàn thành (Definition of Done)

### Verify với `FALAI_MODE=fake` — làm trước, $0
- [x] Upload 1 bộ ảnh nhân vật (slug hợp lệ, chặn slug sai/trùng) → sinh được ảnh keyframe giả, lưu đúng `GeneratedAsset` type=image.
- [x] Ảnh tĩnh + Ken Burns sinh được clip thật (ffmpeg, không fake) — ffprobe: h264, 3s = 90 frame @30fps, 1280x720, `cost_estimate=0`. Cả `zoom_in` và `pan_right`.
- [x] Clip xuất hiện trong kho dùng chung (`asset_service` — nguồn của `AssetPicker`): verify qua HTTP (kho video 0 → 1, file phát được với `video/mp4`) và browser thật (bấm "Thêm vào kho để ghép" → toast → kho 1 → 2).
- [x] Renderer ghép được clip AI Studio: 2 clip → file 5s (3+2) h264 hợp lệ, gọi trực tiếp `ffmpeg.render_timeline()`.
- [ ] **Ghép + render qua UI Timeline Editor** — KHÔNG đạt được: timeline neo vào bảng `Video`, clip AI Studio là `GeneratedAsset` nên không có chỗ neo. Cần chốt hướng (xem Ghi chú "PHÁT HIỆN KHOẢNG TRỐNG KIẾN TRÚC").
- [x] Cache: sinh 2 lần cùng prompt+ref+model → lần 2 trả asset cũ, KHÔNG gọi adapter (test đếm số lần gọi adapter), UI hiện toast "dùng lại". Cache tự bỏ qua khi file đã bị xoá khỏi ổ đĩa.
- [x] Chặn đúng khi vượt ngưỡng $1/lần (409 → Dialog xác nhận, `confirm_expensive` bỏ qua được) và khi vượt hạn mức tháng $30 (402, chặn cứng kể cả đã confirm). Chi tiêu tháng trước không tính vào tháng này.
- [x] Fake adapter mô phỏng 429 (mang `response.status_code=429` thật) và policy-blocked → verify qua `FALAI_FAKE_FORCE_ERROR`. **Chưa verify**: rotation key thật (chưa có adapter thật), nút "Nhờ AI sửa prompt" (chưa làm UI đó).
- [ ] UI progress đúng khi job chạy lâu (fake delay 30-60s), rời trang rồi quay lại vẫn thấy job đang chạy. **Chưa verify** — chạy với delay=0; hiện chỉ có text "có thể rời trang", chưa có job store thật để quay lại xem tiến độ.
- [x] MCP: **client thật qua stdio** spawn `python -m app.mcp_server`, backend live, chạy đủ luồng list refs → cost → keyframe → keyframe lần 2 (cache=True) → Ken Burns → video clip → budget; 3 file tồn tại thật trên đĩa. Token thu hồi → 401; thiếu scope → 403; token rác → 401. **Chưa verify**: hạn mức tháng chặn qua đường MCP (logic dùng chung `_guard_cost` nên có hiệu lực, nhưng chưa chạy thử qua MCP).

### Verify UI trong browser thật (Playwright + Chromium, backend live)
- [x] Trang `/ai-studio` render đúng: sidebar nav, banner fake mode, badge hạn mức tháng, 2 bộ ảnh tham chiếu, 2 lựa chọn tạo clip (Ken Burns mặc định). **0 lỗi console.**
- [x] Prompt có `@mention` sai → hiện cảnh báo đỏ + chặn nút sinh; prompt đúng → hiện "Sẽ đính kèm: @ten (N ảnh)" + mở nút.
- [x] Bấm "Sinh 4 ảnh" → ra 4 thumbnail, chọn được 1 làm keyframe (dấu ✓).
- [x] Bấm "Tạo clip miễn phí" → clip hiện trong player (0:05), lịch sử "Đã tạo (5)" với "Tổng: $0.00 · 5 miễn phí".
- [x] Sửa 2 lỗi UI phát hiện qua ảnh chụp: banner fake mode xuống dòng lởm khởm (150px → 68px), video player chiếm nửa trang (chặn `max-h-72`).
- [x] Nút "Thêm vào kho để ghép" (cạnh player) và "Vào kho" (mỗi dòng lịch sử) → toast xác nhận, kho dùng chung tăng đúng số lượng.

### Verify với API thật — làm cuối, mục tiêu tổng dưới $2
- [ ] 1 ảnh keyframe thật giữ đúng đặc điểm nhân vật từ bộ ảnh tham chiếu (so sánh mắt thường) — mức 2, ~$0.04. Nếu có Gemini free tier thì $0.
- [ ] 1 clip video 4s thật từ keyframe (model rẻ nhất) — mức 3, ~$0.16. Verify hợp lệ bằng ffprobe.
- [ ] 2 clip từ 2 prompt khác nhau, cùng bộ ảnh tham chiếu → nhân vật nhất quán (đánh giá mắt thường) — chỉ làm nếu 2 mục trên đạt, vì đây là mục đắt nhất (~$0.32).
- [ ] Chi phí thực ghi vào `GeneratedAsset` khớp với ước tính đã hiện trước khi bấm (sai lệch nhỏ là bình thường, sai lệch lớn = bug ở `cost_service`).

## Ghi chú phát sinh trong lúc làm

### Phiên 2026-09-09 — backend + MCP xong, frontend chưa làm

**Đã verify thật (không mock)**, ngoài 42 test tự động:
- Ken Burns: `ffmpeg` thật → ffprobe xác nhận h264, đúng thời lượng (3s = 90 frame @30fps), 1280x720. Cả `zoom_in` và `pan_right`.
- Fake adapter: file mp4 ra có **cả video (h264) + audio (aac)** stream → pipeline phía sau xử lý được như file thật. Lỗi mô phỏng 429 mang theo `response.status_code=429` thật nên rotation key Phase 8 nhận diện được.
- API qua HTTP (TestClient): 200 happy path, 400 slug sai, cache trả `from_cache=True` ở lần gọi 2.
- **Scope enforcement qua HTTP thật**: token chỉ có `assets:read` → gọi `/generate/keyframe` bị **403**; token rác → 401; không token (web UI) → 200; sau thu hồi → 401; thu hồi lần 2 → 404.
- **MCP client thật qua stdio**: spawn `python -m app.mcp_server`, backend live trên `:8099`, chạy đủ luồng list refs → cost estimate → keyframe → keyframe lần 2 (cache=True) → Ken Burns (cost=0) → video clip → budget. 3 file sinh ra tồn tại thật trên ổ đĩa.
- Chi phí ước tính khớp con số trong "Chiến lược giảm chi phí": 80 clip 8s/tháng = $256 (Veo) / $64 (Kling) / $25.60 (Luma).

**Lệch khỏi kế hoạch (có lý do)**:
1. **Gộp router**: dùng 1 file `app/api/ai_generation.py` cho cả character-reference và generate (kế hoạch định tách `character_references.py` riêng) — cùng 1 màn hình dùng, tách chỉ thêm chỗ phải nhảy qua lại.
2. **Thêm `app/api/mcp_auth.py`** (ngoài kế hoạch): không có nó thì scope chỉ là trang trí — endpoint sẽ nhận mọi request bất kể token. Đây là lỗ hổng thật nên đã làm luôn.
3. **Thêm `ffmpeg.make_placeholder_image/video()`**: fake adapter ban đầu gọi vào hàm private của ffmpeg adapter (`_escape_drawtext`, `_resolve_default_fontfile`) — vi phạm phân lớp, đã chuyển thành 2 hàm public trong ffmpeg adapter.
4. **MCP không có `create_character_reference`**: upload multipart qua MCP không thực tế (agent không giữ file bytes). Tạo ref làm qua UI.
5. **Thêm `make_ken_burns_clip` vào MCP tool**: để agent có đường miễn phí, không chỉ đường tốn tiền.
6. **`mcp` SDK là 2.x**: `FastMCP` đã đổi tên thành `MCPServer` (`from mcp.server.mcpserver import MCPServer`). Đã cài `mcp` + `ruff` vào venv — **cần thêm vào `requirements.txt`** (chưa làm).

### Phiên 2026-09-09 (tiếp) — frontend xong, verify browser thật

Đã làm: `features/ai-studio/` (5 component: `character-reference-panel`, `generation-settings-panel`, `keyframe-step`, `video-step`, `session-history` + `types.ts`), route `/ai-studio`, sidebar item, ~200 dòng API client trong `lib/api.ts`, endpoint `GET /assets/{id}/file` (thiếu trong kế hoạch).

**Verify trong browser thật** (Playwright + Chromium, backend live trên cổng riêng — không đụng backend :8000 của bạn đang chạy): xem mục "Verify UI trong browser thật" ở Definition of Done. 0 lỗi console. 2 lỗi UI phát hiện qua ảnh chụp đã sửa.

Lưu ý kỹ thuật:
- `routeTree.gen.ts` do vite plugin sinh — thêm route mới xong phải chạy `pnpm exec vite build` (hoặc `dev`) để regenerate, không thì `tsc` báo route không tồn tại.
- Typecheck: **35 lỗi có sẵn trên main** (editor, videos, dashboard, test cũ) không liên quan phase này; code mới thêm 0 lỗi. Đã đối chiếu bằng cách stash code mới rồi đếm lại.
- `networkidle` của Playwright không bao giờ settle trên app này (react-query polling) — dùng `domcontentloaded` + `waitForSelector`.

### Phiên 2026-09-09 (tiếp) — nối vào Timeline Editor

**Phát hiện quan trọng**: `background_library_service` mà kế hoạch nhắc tới **không tồn tại** — Phase 10 chưa bắt đầu nên chưa ai viết nó. `library_service.py` đang có là thư viện video **đã xử lý xong** (bảng `Video`, luồng crawl → dịch → lồng tiếng), không phải kho video nền.

Đích tích hợp đúng là **`asset_service` (Phase 9)**: đọc `features/editor/asset-picker.tsx` thấy Timeline Editor lấy file từ đó, và `asset_service.import_from_path()` đã làm sẵn đúng việc cần (copy file vào kho, tự suy `kind` từ đuôi file → `.mp4` thành `kind="video"`). Nên phần này chỉ cần 1 hàm mỏng + 1 endpoint, không phải dựng service mới.

Chi tiết: `export_to_asset_library()` **copy** chứ không move — bản gốc trong `storage/generated/` phải còn để cache `request_hash` tiếp tục có hiệu lực (move đi thì lần sinh sau sẽ tưởng chưa có và gọi API lại, tốn tiền).

**Còn thiếu / việc tiếp theo**:
- [x] Thêm `mcp>=2.2` và `ruff>=0.16` vào `requirements.txt`.
- [ ] `app/adapters/falai/client.py` — adapter thật. Hiện `FALAI_MODE=real` raise `GenerationError` báo chưa hỗ trợ. Cần key fal.ai thật để làm.
- [x] Section MCP token ở `/api-keys` (`features/api-keys/mcp-token-section.tsx`) + thêm `falai` vào danh sách provider. Verify browser thật: bỏ tick `gen:write` → token đọc được refs (200) nhưng **bị chặn khi sinh nội dung (403)**; bấm thu hồi → badge "Đã thu hồi" + request thành 401. Khối config MCP sinh sẵn kèm đường dẫn Python thật, có nút Copy config.

### Phiên 2026-09-09 (tiếp) — verify render timeline: PHÁT HIỆN KHOẢNG TRỐNG KIẾN TRÚC

**Renderer xử lý được clip AI Studio**: gọi thẳng `ffmpeg.render_timeline()` với 2 clip đã export → ra file 5s (3+2) h264 hợp lệ. Không có vấn đề định dạng.

**Nhưng chưa dùng được qua UI.** Toàn bộ timeline neo vào bảng `Video`:
- `timeline_service.get_timeline/save_timeline/render_timeline_for_video` đều nhận `video_id` và `db.get(Video, video_id)`; render ghi `timeline_rendered_path` trở lại row `Video`.
- Endpoint đều là `/api/videos/{video_id}/timeline...`; editor chỉ vào được qua route `/videos/$videoId`.
- Clip AI Studio là `GeneratedAsset`, **không có row `Video` nào** để neo timeline vào.

⇒ Tiêu chí "kéo clip vào timeline rồi render ra file cuối" **chưa đạt được** và không nằm trong phạm vi đã chốt của phase này. Hai hướng xử lý, cần bạn chốt trước khi làm:

1. **Tạo "project" cho AI Studio** (sạch hơn): bảng riêng `GenerationProject` giữ `timeline_json`, tách timeline khỏi `Video`. Đúng hơn về mặt mô hình nhưng phải tổng quát hoá `timeline_service` cho 2 loại chủ thể.
2. **Cho phép `Video` kiểu "local"** (nhanh hơn): tạo row `Video` không `platform`/`source_url` để chứa timeline. Rẻ nhưng làm bẩn state machine của `Video` — bảng đó đang giả định mọi row đều đi qua pipeline crawl → dịch → lồng tiếng.

Cố ý **không tự chọn** vì đây là quyết định mô hình dữ liệu ảnh hưởng cả Phase 10/13, vượt phạm vi "tích hợp thư viện" ban đầu. Hiện tại clip AI Studio vẫn dùng được ở mọi chỗ khác chọn file từ kho dùng chung (`asset_service`).
- [ ] Job store cho tác vụ chạy lâu: hiện chỉ có text "có thể rời trang" nhưng chưa có cơ chế quay lại xem tiến độ thật (fake delay=0 nên chưa lộ vấn đề; sẽ lộ khi dùng adapter thật mất 1-5 phút).
- [ ] Rotation key `falai` — chưa có gì để rotate khi chưa có adapter thật.
- [ ] Chạy `/code-review` trước khi đánh dấu phase hoàn thành.
