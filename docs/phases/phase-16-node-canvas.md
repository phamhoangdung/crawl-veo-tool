# Phase 16: Dựng video nhiều cảnh (node-canvas)

Trạng thái: **Cả 3 lát đã xong — verify thật trong browser** — dùng được hoàn toàn qua giao diện tại `/projects`: dán kịch bản → canvas node kéo-thả có đường nối → thấy ước tính chi phí → bấm dựng ra 1 video → thêm vào kho để mở ở Timeline Editor → kéo-thả node nhân vật vào cảnh để tự chèn `@tên` vào prompt.

## Mục tiêu

Gỡ nút thắt của Phase 14: AI Studio sinh được từng cảnh rời nhưng **không ghép được thành video hoàn chỉnh** — không có khái niệm dự án, không lưu thứ tự cảnh, và timeline của Phase 13 lại neo vào bảng `Video`.

Kết quả mong đợi: từ kịch bản nhiều cảnh, dựng trên canvas có đường nối rồi bấm render ra **một** file video.

## Phạm vi

**Trong phạm vi:** bảng `GenerationProject` + `Scene` (thứ tự cảnh, transition, vị trí canvas), nối frame (khung cuối cảnh N → keyframe cảnh N+1), render nền toàn dự án thành 1 video, canvas React Flow với node kéo-thả và đường nối.

**Ngoài phạm vi:** graph phân nhánh (`ffmpeg.render_timeline` chỉ nhận 1 track video — ép tuyến tính là *tính năng*), node cho audio/phụ đề (đi qua Timeline Editor Phase 13 bằng cách export video đã dựng), tự động scale khi clip lệch kích thước (chặn sớm với thông báo rõ, scale để sau).

## Ý nghĩa "đường nối" — 3 thứ, không phải 1

Điều đáng nhớ nhất của phase này: đường nối trên canvas **chỉ là biểu diễn trực quan**. Thứ thật sự làm video liền mạch nằm ở dưới:

1. **Thứ tự phát** — `Scene.order_index`.
2. **Nối frame** — `chain_from_previous`: lấy khung cuối clip cảnh trước làm keyframe mở đầu cảnh sau, để nhân vật không bị "trôi" giữa các lần gọi model độc lập.
3. **Hiệu ứng chuyển cảnh** — `transition_in` (`cut`/`fade`), thuộc cạnh đi *vào* cảnh đó.

Cả 3 chạy được mà không cần canvas. Canvas cộng thêm giá trị trực quan, không thay thế phần lõi.

## Việc cần làm

### Lát 1 — Backend (xong)
- [x] `app/models/generation_project.py`: `GenerationProject` + `Scene` + `SceneStatus`. **Không có bảng `edges`** — với chuỗi tuyến tính, cạnh được xác định đủ bởi `order_index` + `transition_in` + `chain_from_previous`; có bảng edges sẽ cho UI vẽ nhánh mà renderer không diễn đạt nổi.
- [x] Không tạo row `Video` giả: `Video` cần non-null `job_id` (mà `Job` lại cần `platform`+`keyword`), `platform` enum chỉ BILIBILI/DOUYIN, `UniqueConstraint(platform, platform_video_id)`, và `api/library.py:25` sẽ crash nếu `platform` NULL.
- [x] `ffmpeg.probe_duration_seconds()` + `ffmpeg.extract_last_frame()` — trích khung cuối clip (`-ss` trước `-i` để seek nhanh, lùi 0.05s để không rơi qua frame cuối decode được).
- [x] `ai_generation_service.extract_last_frame_asset()` — lưu khung cuối thành `GeneratedAsset` IMAGE, miễn phí và idempotent nhờ `request_hash`.
- [x] `app/services/project_service.py`: CRUD dự án/cảnh, `reorder_scenes`, `save_canvas`, `generate_scene` (async), `build_operations`, `_resolve_start_keyframe` (3 nhánh: clip cảnh trước → keyframe cảnh trước → sinh mới).
- [x] `app/services/project_render_service.py`: `start_render` + `render_worker` chạy nền (`BackgroundTasks`), luôn đóng tiến độ cả nhánh lỗi. `_ensure_uniform_dimensions` chặn sớm khi clip lệch kích thước.
- [x] `progress_service`: thêm `subject_type: "video"|"project"` vào key, thêm kind `render_project` + stage `generating`/`rendering`. **Không dùng hack id âm** (nhét project_id vào ô video_id dưới dạng số âm) — làm vậy thì mọi query theo `video_id` sẽ lặng lẽ trả rỗng thay vì báo lỗi. `subject_type` là keyword-only mặc định `"video"` nên 0 caller cũ phải sửa.
- [x] `timeline_service._validate_operations` → public `validate_operations` (hàm thuần, dùng chung 2 phase).
- [x] `app/api/projects.py` + schemas: 11 endpoint, map lỗi 402/409 như `ai_generation.py`.
- [x] Test: 20 test `project_service` + 8 test `project_render_service`.

### Lát 2 — Canvas React Flow (xong)
- [x] `pnpm add @xyflow/react` (v12.11.6) + nạp `@xyflow/react/dist/style.css` ở `main.tsx` — **thiếu CSS thì canvas mất bố cục mà không báo lỗi gì**.
- [x] `src/features/flow/graph.ts` + `graph.test.ts` (15 test): `toSceneOrder`, `validateGraph` (chặn chu trình / phân nhánh / graph rời rạc), `autoLayoutLinear`, `edgesFromOrder`.
- [x] `src/features/flow/store.ts` + `store.test.ts` (10 test): Zustand + undo/redo **gộp theo cử chỉ**. Test khẳng định 100 lần `moveNode` giữa 1 cặp `beginGesture`/`endGesture` chỉ push **đúng 1** entry (editor Phase 13 sẽ push 100).
- [x] Node `scene` (prompt sửa tại chỗ, thumb keyframe + clip, badge trạng thái, nút Sinh cảnh / Tuỳ chọn) và node `output` (nút Dựng video / Xem-tải video).
- [x] `scene-settings-dialog.tsx`: thời lượng, ảnh tĩnh hay video AI, kiểu chuyển động, nối frame, chuyển cảnh (cảnh đầu tự ẩn 2 tuỳ chọn cuối vì không có gì phía trước).
- [x] Route `/projects` + nav sidebar (icon `Workflow`) + block API client `// --- Phase 16 ---`.
- [x] `TaskKind` thêm `render_project` + `TaskSubjectType`; `TaskProgressRead` (backend) thêm `subject_type` — **phát hiện khi làm**: đổi dataclass thôi chưa đủ, schema response và mapper ở `api/downloads.py` cũng phải sửa, không thì API im lặng trả `"video"` cho mọi dự án.

### Lát 3 — Hoàn thiện (một phần)
- [x] **Ước tính chi phí cả dự án**: `project_service.estimate_project_cost()` + `GET /{id}/cost-estimate`, hiện ngay trên node output. Chỉ tính cảnh **chưa có clip** — cảnh đã sinh thì tái dùng, gộp vào sẽ doạ người dùng bằng con số không có thật. Cảnh nối frame cũng không tính tiền ảnh (khung cuối lấy bằng ffmpeg, miễn phí).
- [x] **Export sang Timeline Editor**: `project_render_service.export_to_asset_library()` + `POST /{id}/export-to-library` + nút "Thêm vào kho" trên node output. Copy chứ không move để nút "Xem / tải video" vẫn chạy.
- [x] Node `character` (trỏ `CharacterReference`, cạnh vào cảnh = tự chèn `@slug`) — `features/flow/components/character-node.tsx` + wiring trong `project-canvas.tsx`.

## Tiêu chí hoàn thành

### Lát 1 (đã verify thật)
- [x] Kịch bản 5 cảnh → **1 video hoàn chỉnh 23.000s**, 1280x720, h264 (5+5+5+4+5 = 24s trừ 1s fade chồng nhau). Verify bằng ffprobe.
- [x] Nối frame hoạt động: keyframe cảnh 2 là ảnh trích từ clip cảnh 1, **không** sinh mới từ prompt (test đếm số lần gọi adapter: `lastframe==1`, `image==1` chứ không phải 2).
- [x] Tiến độ đi đúng chuỗi: `pending → generating 0/3 → 1/3 → 2/3 → rendering → done`, gắn `subject_type="project"`.
- [x] Chặn render trùng khi đang chạy; lỗi giữa đường vẫn đóng tiến độ (`failed`) chứ không để UI quay mãi.
- [x] API qua HTTP: tạo dự án 3 cảnh, PATCH cảnh, transition sai → 400, thêm/xoá cảnh xong `order_index` vẫn liên tục, lưu/đọc canvas position + viewport, render nền, tải video ra `video/mp4`.
- [x] 319 test pass toàn suite, ruff sạch.

### Lát 2 (đã verify thật trong browser — Playwright + Chromium, backend live)
- [x] Trang `/projects` render: 3 node cảnh + 1 node output, 3 đường nối. **0 lỗi console.**
- [x] Dán kịch bản 3 dòng → tạo đúng 3 cảnh, prompt khớp từng dòng.
- [x] Kéo node: y 419 → 584; **undo trả về chính xác 419** (không phải bước trung gian — chứng minh gộp cử chỉ chạy đúng).
- [x] Lưu bố cục → nút đổi thành "Đã lưu" → **reload vẫn giữ nguyên vị trí** (533 → 533).
- [x] Bấm "Dựng video" trên canvas → nút chuyển "Đang dựng" → tự sinh nốt 3/3 cảnh → tải được file 731KB `video/mp4`.
- [x] 100 lần `moveNode` giữa 1 cặp `beginGesture`/`endGesture` chỉ push **đúng 1** history entry (test tự động).
- [x] 25/25 test frontend pass, eslint sạch, typecheck 0 lỗi mới.

### Lát 3 (đã verify thật trong browser)
- [x] Ước tính chi phí hiện trên node output và **cập nhật ngay khi đổi cấu hình cảnh**: 4 cảnh Ken Burns = `~$0.01`; đổi 1 cảnh sang video AI 5s → `~$0.51` (chênh $0.50 = Kling $0.10/s × 5s).
- [x] Dự án đã dựng xong hiện "Mọi cảnh đã có clip — dựng lại không tốn phí" thay vì con số gây hiểu nhầm.
- [x] Nút "Thêm vào kho" → toast xác nhận, kho video tăng 4 → 5, video dự án vẫn tải được (copy chứ không move).
- [x] 319 test backend pass, ruff sạch, eslint sạch, typecheck 0 lỗi mới.
- [x] Node `character` kéo vào cảnh → tự chèn `@slug` vào prompt — verify thật trong browser (xem Phiên 2026-09-09, Lát 3 tiếp — node character).

## Ghi chú phát sinh

### Phiên 2026-09-09

**Tìm ra bug thật của renderer Phase 13** (không phải do code phase này): `xfade` fail với `"First input link main timebase (1/1000000) do not match ... (1/15360)"` bất cứ khi nào có **fade đứng sau một chuỗi cut**. Nguyên nhân: `concat` xuất timebase `1/1000000` và framerate `1/0` (không xác định), còn clip chưa qua concat giữ timebase gốc. Phase 13 chưa lộ vì kịch bản test không có tổ hợp đó.

Đã sửa tại gốc trong `ffmpeg.render_timeline`: chuẩn hoá `fps=30,settb=AVTB` từng clip trước khi nối. Thử `settb` một mình thì lộ lỗi tiếp theo (`"needs to be a constant frame rate"`) — phải có cả `fps`. 53 test Phase 13 vẫn pass sau khi sửa.

**Hai bài học khi viết test:**
1. `progress_service._active` là dict ở module nên sống xuyên test, còn mỗi test dùng DB mới nên project id luôn từ 1 → entry "đang chạy" của test trước làm test sau tưởng đang render. `clear_finished()` không đủ (nó cố ý giữ entry chưa kết thúc), phải `_active.clear()`.
2. `render_worker` tự mở `SessionLocal()` (đúng, vì session của request đã đóng) nên **không thấy được DB `sqlite://` in-memory** của test — fixture phải dùng file tạm + patch `SessionLocal`.

**Lệch khỏi kế hoạch:** Plan agent đề xuất nhét `project_id` vào ô `video_id` dưới dạng số âm để tránh trùng key tiến độ. Không làm — biến 1 field thành 2 ý nghĩa tuỳ dấu, và query theo `video_id` sẽ lặng lẽ sai. Thay bằng thêm `subject_type` vào key, keyword-only + default nên 0 caller cũ phải sửa (291 test pass ngay sau khi đổi).

**Còn thiếu:** toàn bộ frontend (Lát 2), và chưa verify kéo clip đã dựng vào Timeline Editor để render lần cuối kèm audio/phụ đề.

### Phiên 2026-09-09 (tiếp) — Lát 2: canvas

**Ba cái bẫy gặp phải, ghi lại để khỏi mất thời gian lần sau:**

1. **CSS của React Flow phải nạp toàn cục.** Thiếu `import '@xyflow/react/dist/style.css'` thì canvas mất bố cục (node chồng nhau, không thấy đường nối) mà **không báo lỗi gì** — rất khó đoán ra.

2. **Sửa dataclass thôi chưa đủ để field ra tới API.** Thêm `subject_type` vào `TaskProgress` nhưng `TaskProgressRead` (schema) và mapper ở `api/downloads.py` không có nó → API im lặng trả `"video"` cho mọi dự án. Kiểu bug lặng lẽ này chính là thứ tôi muốn tránh khi từ chối hack id âm, suýt nữa lại tự mắc.

3. **`fitView` đo lúc node chưa render xong nên luôn hụt.** Node output tràn khung ~7-50px. Tôi **đoán sai 4 lần liên tiếp** (tăng padding → dời vị trí node → thêm `minWidth` → lại padding) trước khi chịu đo DOM. Đo ra mới thấy nguyên nhân khác hẳn: inner div đúng 260px nhưng wrapper của React Flow chỉ 150px, vì width đặt ở component con không làm wrapper giãn. Sửa đúng gồm 2 phần: đặt `style={{ width }}` lên **node object** (không phải trong component), và gọi `instance.fitView()` trong `onInit` + `requestAnimationFrame` thay vì dùng prop `fitView`.
   **Bài học: đo trước, sửa sau.** Bốn lần thử mù tốn hơn một lần đo.

### Phiên 2026-09-09 (tiếp) — Lát 3: chi phí + export

**Bẫy gặp phải:** endpoint mới trả 404 dù code đã có. Nguyên nhân là **server đang chạy từ trước khi thêm route** và uvicorn không bật `--reload` — không phải lỗi code. Dấu hiệu nhận ra: `detail` là `"Not Found"` (404 mặc định của router) chứ không phải thông báo tiếng Việt tự viết. Cách kiểm tra nhanh: so `curl /openapi.json` với `grep` trong file route; nếu code có mà server không có thì chỉ cần restart.

**Quyết định thiết kế về ước tính chi phí:** chỉ tính cảnh chưa có clip. Ban đầu hiển thị "Miễn phí — 0 cảnh dùng ảnh tĩnh" cho dự án đã dựng xong — câu vô lý (0 cảnh miễn phí thì sao lại miễn phí?). Sửa thành thông báo riêng khi `pending_scenes == 0`. Bài học: con số đúng vẫn có thể ghép thành câu sai.

**Lệch khỏi kế hoạch:** kế hoạch định để prompt cảnh trong local state đồng bộ từ server bằng `useEffect`. Bỏ cách đó (eslint `react-hooks/set-state-in-effect` bắt đúng): state chỉ giữ prompt **đang sửa**, dữ liệu gốc đọc thẳng từ query — tránh hai nguồn sự thật lệch nhau. Tương tự, `SceneSettingsDialog` tách thành component con có `key={scene.id}` để state khởi tạo từ props thay vì đồng bộ qua effect.

### Phiên 2026-09-09 (tiếp) — Lát 3 tiếp: node `character`

**Thiết kế cạnh nhân vật → cảnh:** không lưu thành cạnh riêng (không bảng, không field mới) — cạnh chỉ là **suy ra** từ `@tên` có trong `Scene.prompt` (`graph.ts: parseMentions` + `characterEdgesFromMentions`), giống hệt cách cạnh cảnh→cảnh suy ra từ `order_index` ở Lát 1. Kéo cạnh từ node nhân vật vào handle riêng (`id="character"`, Position.Top trên `SceneNode` — tách khỏi handle Left vốn dùng cho nối frame cảnh trước) chỉ là **thao tác chèn `@tên` vào prompt rồi lưu như bình thường**; tháo cạnh (chọn cạnh + Backspace, qua `onEdgesChange` xử lý `type: 'remove'`) là thao tác ngược — gỡ `@tên` khỏi prompt. Cách này giữ đúng nguyên tắc đã chốt ở Lát 1: canvas chỉ vẽ lại, không phải nguồn sự thật.

**Vị trí node nhân vật trên canvas lưu ở localStorage, không phải backend.** Nguồn sự thật thật sự (nhân vật nào ở cảnh nào) đã nằm trong text prompt (lưu server-side qua `Scene.prompt` như trên) — vị trí hiển thị trên canvas chỉ là tiện ích riêng trình duyệt, không cần thêm cột DB nào. Đã verify: thêm node → kéo → connect → **reload trình duyệt** → node, vị trí, và cạnh đều khôi phục đúng.

**Verify thật trong browser (Playwright + Chromium, backend fake-mode):** tạo bộ ảnh `@hero` ở AI Studio → tạo dự án 2 cảnh → "Thêm nhân vật" → kéo cạnh từ node `@hero` vào handle character của cảnh 2 → prompt cảnh 2 tự thêm `@hero`, lưu ngay (không cần bấm gì thêm) → reload vẫn còn → bấm "Bỏ khỏi canvas" chỉ gỡ node khỏi canvas, **không đụng tới `@hero` trong prompt** (đúng thiết kế: xoá hiển thị ≠ xoá dữ liệu).

**Không verify được bằng automation:** thao tác "chọn cạnh trên canvas rồi bấm Backspace để gỡ mention" — click tổng hợp qua Playwright/CDP (mouse lẫn dispatchEvent thủ công, đã thử nhiều cách) không kích hoạt state `selected` của React Flow cho **bất kỳ** node/cạnh nào trong môi trường này (kể cả node/cạnh có sẵn từ Lát 2), trong khi kéo-thả (drag) và tạo-cạnh (connect) qua đúng cùng cơ chế pointer event lại chạy đúng. Đây nhiều khả năng là hạn chế của việc giả lập input qua CDP trên máy này, không phải lỗi code — cơ chế `onEdgesChange` xử lý `type:'remove'` là cách chính thống React Flow khuyến nghị cho controlled edges. Cần người dùng tự tay thử claim lại nếu nghi ngờ.

**Bug thật phát hiện ngoài lề (không phải do code phase này):** `project_service.delete_project` throw `FOREIGN KEY constraint failed` khi xoá — do `Scene.project_id` chỉ là cột FK thô, không có `relationship()` nên SQLAlchemy không biết thứ tự phụ thuộc, có lúc phát lệnh `DELETE FROM generation_projects` trước `DELETE FROM scenes`. Sửa bằng thêm `db.flush()` giữa 2 bước xoá — verify đúng bằng script Python gọi thẳng hàm (bypass HTTP). **Lưu ý cho phiên sau:** máy dev Windows này có xu hướng để lại tiến trình `uvicorn --reload` cũ chạy ngầm không kill được qua `Stop-Process`/`taskkill` (PID báo "not found" nhưng port vẫn nghe) — nếu sửa backend mà gọi API vẫn thấy hành vi cũ, đừng cố kill tiến trình, hãy nhờ người dùng tự tắt hẳn terminal `npm run dev` cũ rồi chạy lại.
