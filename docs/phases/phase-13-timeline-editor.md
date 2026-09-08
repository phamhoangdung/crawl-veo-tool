# Phase 13: Trình chỉnh sửa timeline (AI gợi ý + kéo-thả thủ công)

Trạng thái: **Xong & verify thật** (test suite backend + browser thật cho frontend, ffmpeg thật) — trừ 1 điều chỉnh phạm vi (xem Ghi chú: không thay `subtitle-editor.tsx`, để cả 2 cùng tồn tại vì phục vụ 2 mục đích khác nhau).

## Nguyên tắc cốt lõi (chốt cùng bạn)
AI chỉ đưa **gợi ý** (mốc cắt clip, đoạn video nền, vị trí chèn commentary...), hiển thị sẵn trên timeline dưới dạng chỉnh sửa được — không tự động render. Người dùng chấp nhận nguyên trạng hoặc tự kéo-thả điều chỉnh, bấm nút riêng để render. Đây là component **dùng chung** cho Phase 9/10/11.

## Mục tiêu
Xây timeline đa track chạy trong web UI hiện có (và trong desktop app ở Phase 12), có preview trực tiếp, xuất file qua ffmpeg backend đã có (mở rộng thành bộ dựng filter graph động).

## Phạm vi
**Trong phạm vi:** timeline đa track (video chính, giọng đọc, nhạc nền, caption/overlay), trim/cắt/kéo sắp xếp lại đoạn, hiển thị waveform audio, overlay text kéo-thả vị trí trên khung hình, chuyển cảnh cơ bản (cắt cứng/fade) giữa các đoạn video, chỉnh âm lượng riêng từng track audio, preview trực tiếp trong trình duyệt, xuất qua ffmpeg backend.

**Ngoài phạm vi:** hiệu ứng hình ảnh, thư viện transition nâng cao, chỉnh màu, template, đa lớp compositing phức tạp, render tăng tốc GPU trong trình duyệt, kéo-thả sắp xếp lại THỨ TỰ clip video (chỉ resize 2 đầu — đổi thứ tự cần sửa tay JSON/gọi API, chưa có UI).

## Nguyên liệu — quyết định đã chốt khi code
- [x] **Hướng dựng UI timeline**: tự build tối giản (SVG/div + Zustand + pointer events thuần) — đúng đề xuất, không fork OpenCut/React Video Editor.
- [x] **Mô hình dữ liệu "edit operations"**: `{ tracks: [{ type: 'video'|'audio'|'overlay', role?, clips: [...] }] }`. Video: `source/start/end/transition_in/transition_duration` (start/end là đoạn TRIM trong file nguồn, vị trí trên timeline tổng suy ra từ thứ tự clip). Audio: thêm `track_start/volume` (vị trí + âm lượng khai báo trực tiếp). Overlay: `text/start/end/x/y/font_size` (x/y là **toạ độ tâm chữ** theo tỉ lệ khung hình [0,1], không phải mép hộp).
- [x] **Waveform**: tính ở backend (`waveform_service.py`, dùng `pydub` đọc PCM tính peak theo bucket) — đúng đề xuất.

## Việc đã làm

### Backend
- [x] `app/adapters/ffmpeg.py::render_timeline()` — dựng `filter_complex` động: `trim`+`setpts` từng clip video, `concat`/`xfade` nối clip, `drawtext` cho overlay (có `enable='between(t,...)'`), `atrim`+`adelay`+`volume`+`amix` cho nhiều track audio.
- [x] `crop_vertical()` — crop tĩnh (chuẩn bị sẵn cho Phase 11).
- [x] `app/services/waveform_service.py` — `compute_waveform()` dùng `pydub`, chuẩn hoá peak về [0,1].
- [x] `app/services/timeline_service.py` — `get_timeline`/`save_timeline` (validate + lưu draft, KHÔNG render), `render_timeline_for_video` (chỉ gọi khi user chủ động).
- [x] `app/models/video.py` + migration (`db.py::ensure_schema_columns`): thêm `timeline_json`, `timeline_rendered_path`.
- [x] `app/api/timeline.py`: `GET/PUT /api/videos/{id}/timeline`, `POST /api/videos/{id}/timeline/render`, `GET /api/videos/{id}/waveform`.
- [x] Test **ffmpeg thật** (`tests/adapters/test_ffmpeg.py`, 7 test) — dựng clip synthetic bằng `ffmpeg -f lavfi` (testsrc/sine), verify qua `ffprobe`: single-clip, hard-cut nối clip, fade transition rút ngắn tổng thời lượng đúng công thức, mix nhiều track audio, overlay không phá lệnh render, crop đúng kích thước.
- [x] Test `timeline_service` (13 test) + `waveform_service` (5 test, verify sine wave có peak, silence gần 0).

### Frontend
- [x] `features/editor/layout.ts` — hàm thuần: tính vị trí clip video trên timeline tổng (`computeVideoTrackLayout`, khớp đúng công thức backend), `applyDragToClip` (tính patch khi kéo, tách biệt theo track type/drag mode) — **15 test thuần** không cần browser.
- [x] `features/editor/store.ts` — Zustand, state = edit operations + clip đang chọn.
- [x] `features/editor/timeline.tsx` — render đa track, kéo resize 2 đầu (video/audio) + kéo di chuyển thân clip (audio: đổi `track_start`; overlay: đổi `start`+`end`; video: không hỗ trợ move, chỉ resize vì vị trí do thứ tự quyết định), waveform canvas nền cho track audio đầu tiên.
- [x] `features/editor/overlay-layer.tsx` — hộp text kéo-thả trên khung preview, toạ độ tâm khớp công thức backend.
- [x] `features/editor/waveform-canvas.tsx` — vẽ canvas từ mảng peak.
- [x] `features/editor/index.tsx` (`TimelineEditor`) — ghép tất cả + nút "Dùng gợi ý AI" (dựng timeline mặc định từ pipeline đã có: video gốc + audio đã lồng tiếng + phụ đề dịch thành overlay caption) + "Lưu" (tách biệt) + "Render" (tách biệt) + bảng chỉnh chi tiết bằng số (`ClipInspector`, chính xác hơn kéo chuột).
- [x] Gắn vào `video-detail.tsx`: Card mới "Trình chỉnh sửa timeline" mở Dialog lớn chứa `TimelineEditor` — xem Ghi chú về việc **giữ nguyên** `SubtitleEditor` cũ.
- [x] Test browser thật (Playwright, 6 test) cho `Timeline`: render đúng clip, vị trí clip 2 đúng sau hard-cut, chọn clip qua pointerdown, **kéo cạnh phải audio clip kéo dài `end` thật**, **kéo thân audio clip đổi `track_start` thật**, trạng thái rỗng.

## Tiêu chí hoàn thành (Definition of Done)
- [x] Mở 1 video có gợi ý AI → thấy hiện sẵn trên timeline, kéo chỉnh được — verify qua test browser thật (pointer drag thay đổi đúng state).
- [x] Thêm overlay text kéo-thả vị trí, render đúng vị trí đã đặt — verify công thức x/y khớp giữa frontend (`overlay-layer.tsx`) và backend (`drawtext x=w*fx-text_w/2`), render không lỗi qua test ffmpeg thật.
- [x] Có transition (fade) giữa 2 đoạn video nền — verify bằng ffprobe thật (`test_fade_transition_shortens_total_duration`, tổng thời lượng ngắn hơn cộng đơn giản đúng theo `transition_duration`).
- [x] Chỉnh âm lượng riêng track nhạc nền — field `volume` per-clip, verify `amix` chạy đúng qua ffmpeg thật (`test_mixes_multiple_audio_tracks`).
- [x] Không thao tác nào tự render khi chưa bấm nút riêng — verify qua test (`test_does_not_render_automatically_on_save`) + code: `save_timeline`/`saveTimeline` không gọi `render_timeline` ở đâu cả.

## Ghi chú phát sinh trong lúc làm
- **KHÔNG thay thế `subtitle-editor.tsx`** như kế hoạch ban đầu ghi — phát hiện ra 2 tool phục vụ 2 mục đích khác nhau: `SubtitleEditor` sửa `translated_text` dùng để **sinh giọng đọc TTS** (ảnh hưởng bước dubbing ở Phase 2), còn track "overlay" ở timeline editor mới là **caption hiển thị trực quan** trên bản render cuối (không ảnh hưởng giọng đọc). Xoá `SubtitleEditor` sẽ mất tính năng sửa bản dịch trước khi lồng tiếng — quyết định giữ cả 2, thêm entry point riêng ("Trình chỉnh sửa timeline") thay vì gộp.
- **Bug ffmpeg thật phát hiện khi test, không phải chỉ lỗi lý thuyết**: filter `drawtext` (overlay text) **CRASH** (access violation, không phải lỗi cú pháp thường) trên máy dev vì thiếu file cấu hình fontconfig ("Fontconfig error: Cannot load default config file"). Sửa bằng cách **chỉ định `fontfile` trực tiếp** (dò `C:\Windows\Fonts\arial.ttf` hoặc tương đương macOS/Linux) thay vì để filter tự dò qua fontconfig. Đáng chú ý cho Phase 12 (đóng gói desktop): ffmpeg portable đóng gói sẵn nhiều khả năng cũng thiếu fontconfig y hệt — fix này giúp tránh crash tương tự khi đóng gói.
- **Sửa lại công thức toạ độ overlay giữa lúc làm**: bản đầu dùng `(w-text_w)*x` (neo theo mép hộp chữ) — đổi sang `w*x-text_w/2` (neo theo **tâm** hộp chữ) để khớp đúng trực giác kéo-thả ở frontend (kéo đặt điểm giữa, không phải mép), tránh lệch vị trí giữa preview và bản render thật ở các giá trị x/y gần 0 hoặc 1.
- **Bug React Compiler lint (`react-hooks/refs`)**: pattern ban đầu (hàm factory `beginDrag(mode)` trả về closure ghi vào `useRef` bên trong) bị coi là "truy cập ref lúc render" dù thực chất chỉ chạy khi có sự kiện chuột thật. Sửa bằng cách tách 1 handler ổn định (`handlePointerDown`, đọc `mode` từ `data-drag-mode` attribute) thay vì tạo closure mới mỗi lần render — sạch lint, code cũng rõ ràng hơn.
- **Migration `videos` table**: thêm cột `timeline_json`/`timeline_rendered_path` qua `ensure_schema_columns()` (ALTER TABLE ADD COLUMN, không cần dựng lại bảng như Phase 8 vì không đụng constraint) — verify trên **DB thật** (115 video có sẵn), dữ liệu giữ nguyên.
- **Playwright browser chưa cài sẵn trong môi trường** — phải chạy `pnpm exec playwright install chromium` trước khi test browser chạy được lần đầu (nếu máy bạn build lại từ đầu/CI mới, nhớ bước này — đã có sẵn script `test:browser:install` trong `package.json`).
- **Waveform trong Timeline UI**: chỉ hiển thị cho track audio ĐẦU TIÊN (thường là giọng đọc) — đơn giản hoá cho MVP, chưa tính waveform riêng biệt cho từng clip/track audio khác nhau (vd nhạc nền sẽ không có waveform riêng, dù vẫn kéo-chỉnh được bình thường).
- **Không hỗ trợ kéo đổi THỨ TỰ clip video** (chỉ resize 2 đầu) — vị trí clip video trên timeline tổng suy ra từ thứ tự trong mảng, đổi thứ tự cần thao tác khác (kéo-thả sắp xếp lại mảng) chưa làm ở bản này; đủ dùng cho nhu cầu hiện tại (trim/cắt), có thể bổ sung sau nếu Phase 10 cần sắp xếp lại nhiều đoạn nền thường xuyên.

## Sửa UX + tách track audio (phiên 2026-09-08)

**Editor bắt "thêm video" dù đang ở trang chi tiết video.** `previewSource` đọc từ `operations.tracks` — tức timeline ĐÃ LƯU. Video chưa lưu timeline nào thì `operations` rỗng → hiện "Chưa có video", phải bấm "Dùng gợi ý AI" mới thấy gì. Sửa: query timeline tự dựng gợi ý khi `getTimeline` trả rỗng, người dùng vào là thấy ngay nội dung.

Kèm 2 lỗi phát hiện lúc sửa:
- `getTimeline` trả **`null`** (không phải mảng rỗng) khi chưa có timeline — code gọi `.length` sẽ nổ.
- URL preview hardcode `variant=dubbed`, video chưa lồng tiếng thì khung preview hỏng. Đổi sang chọn theo `dubbed_path` có hay không.

**Bỏ popup.** Editor chuyển từ Dialog sang section full-width ngay trong trang chi tiết, đặt dưới 2 cột — nó cần nhiều chiều ngang, nhét vào cột phải hoặc popup đều chật.

**Chỉnh âm lượng giọng đọc / nhạc nền riêng.** Trước đó gợi ý AI dùng `dubbed.mp4` làm 1 track audio duy nhất — file này đã trộn sẵn nên không tách âm lượng được. Nhưng pipeline vốn đã ghi ra 2 file riêng: `voice_timeline.mp3` (giọng đọc) và `demucs_out/htdemucs/original_audio/no_vocals.wav` (nhạc nền tách bằng demucs).

- `GET /api/videos/{id}/audio-stems` trả đường dẫn 2 stem đó (+ `mixed` làm dự phòng khi chưa chạy lồng tiếng).
- Gợi ý AI dựng **2 track audio riêng**: giọng đọc volume 1.0, nhạc nền volume 0.3 (để nhỏ hơn cho khỏi át lời).
- `volume-mixer.tsx`: thanh trượt + nút tắt tiếng cho từng track, **luôn hiện** dưới khung preview — khác `ClipInspector` phải chọn clip mới thấy. Dùng `input[type=range]` thuần vì dự án chưa có component Slider.
- Backend không phải sửa: `render_timeline` vốn đã `amix` nhiều track với volume riêng. Verify render thật 2 track (1.0 + 0.3) ra file có audio stream AAC.

## Nâng editor lên mức dùng được thật (phiên 2026-09-08, phần 2)

**Chọn clip giờ tua video tới đúng giây bắt đầu clip đó.** Trước chỉ đổi state, không biết đang sửa đoạn nào. Timeline và thẻ `<video>` nằm ở 2 component khác nhau nên đi qua store: `requestSeek(seconds)` đặt `{seconds, nonce}`, preview hưởng ứng rồi `consumeSeek()`. Dùng nonce chứ không phải số trần để **chọn lại đúng clip cũ vẫn tua lại được**.

**Điều khiển cơ bản** (`toolbar.tsx` + `hooks/use-editor-shortcuts.ts`):
- **Playhead** — vạch đỏ theo thời điểm đang phát, phủ mọi track. `pointer-events-none` để không chặn kéo clip.
- **Thước thời gian** — bấm để tua. Mốc thưa dần khi zoom out (1s → 5s → 15s → 60s) cho khỏi chi chít chữ.
- **Zoom** 5–400 px/giây. `PX_PER_SECOND` từ hằng số cố định đổi thành tham số của `secondsToPx`/`pxToSeconds` (giữ export cũ để test hiện có không vỡ). Listener kéo gắn 1 lần nên không thấy zoom mới → đồng bộ qua ref **trong effect**, không ghi lúc render (lint `react-hooks/refs` chặn đúng).
- **Undo/redo** 50 bước. Thao tác mới xoá nhánh redo; nạp timeline mới (server/gợi ý AI) xoá sạch lịch sử vì đó là điểm bắt đầu mới.
- **Phím tắt**: Space play/pause, S cắt đôi, Delete xoá, Ctrl+D nhân bản, Ctrl+Z / Ctrl+Shift+Z, mũi tên trái/phải nhích 1 frame (Shift = 5 giây). Bỏ qua khi đang gõ trong input.

**Thao tác cắt/ghép**:
- **Cắt đôi tại playhead** — quy đổi vị trí output về offset trong file nguồn (audio phải trừ `track_start`), clip sau được dời `track_start` tương ứng. Bỏ qua khi cắt sát mép để không tạo clip 0 giây.
- **Nhân bản** — bản sao audio dời ra sau bản gốc để không chồng tiếng.
- **Đổi thứ tự clip video** — nút ←/→ (hạn chế cũ đã gỡ). Chỉ hiện với track video vì audio/overlay đã có `track_start`/`start` riêng.
- 13 test store thuần cho các thao tác này, gồm ca khó: split clip audio phải dời `track_start` đúng.

**Tab Phụ đề chạy theo video** (`subtitle-review.tsx`): video bên trái, danh sách câu bên phải tự cuộn và tô sáng câu đang phát, bấm câu để nhảy tới đoạn đó. Có nút tắt tự-cuộn (người dùng có thể muốn đọc chỗ khác trong lúc video chạy). Chọn biến thể phát theo thứ tự burned → dubbed → original.

**Còn thiếu** (chưa làm trong phiên này): preview chưa phản ánh đúng bản render (vẫn phát 1 file gốc, không thấy hiệu ứng cắt/chuyển cảnh/trộn âm lượng); chưa thêm ảnh/logo/watermark, nhạc nền từ file ngoài, chỉnh tốc độ phát, fade in/out âm thanh; chưa snap khi kéo.
