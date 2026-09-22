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

## Che logo/phụ đề gốc + khung phụ đề (2026-09-08)
- Track `blur` mới: che logo hoặc phụ đề tiếng Trung có sẵn trong video gốc. Toạ độ theo **tỉ lệ khung hình** [0,1] nên đúng chỗ dù video đổi độ phân giải. Hai chế độ: `blur` (gblur) và `pixelate` (thu nhỏ rồi phóng to bằng nội suy neighbor — che chữ tốt hơn vì không còn nét chữ).
- **Áp TRƯỚC overlay text và ảnh**: mục đích là che thứ có sẵn trong video gốc; làm sau thì mờ luôn chữ và logo mình vừa thêm. Có test kiểm tra thứ tự này.
- **`gblur` chứ không `boxblur`**: boxblur giới hạn radius theo kích thước vùng cắt (vùng 80x36px chỉ cho radius < 18) nên vùng che nhỏ lỗi hẳn — phát hiện khi render thật, đã có test cho ca này.
- **Phải `split` trước khi phân nhánh**: ffmpeg không cho dùng lại cùng một nhãn cho 2 nhánh filter (một nhánh cắt vùng làm mờ, một nhánh làm nền).
- Khung giới hạn phụ đề (`box_width` theo tỉ lệ): `drawtext` KHÔNG tự xuống dòng nên phải tự wrap ở Python. Cắt theo từ với tiếng Việt, cắt cứng với tiếng Trung (không có dấu cách giữa chữ). Bề rộng video đọc bằng `probe_video_width` (fallback 1080).
- Verify thật bằng đo pixel: vùng blur đúng **x 0.253-0.747, y 0.250-0.746** so với yêu cầu 0.25-0.75, không tràn. Khung phụ đề: không giới hạn thì chữ tràn **100%** khung hình (bị cắt 2 đầu), `box_width=0.5` thì gọn trong **0.39** và tự chia 6 dòng.
- Kéo-thả phụ đề đã có sẵn từ trước (`OverlayLayer`), không cần làm lại.

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

## Watermark kéo-thả + kiểu chữ phụ đề (phiên 2026-09-21)

**Yêu cầu**: thêm watermark/logo và vùng làm mờ để che watermark gốc — cả 2 tự kéo-thả; tuỳ chỉnh vị trí/font/màu/đậm cho phụ đề, áp cho cả Timeline Editor và luồng "Ghép phụ đề vào video" (burn_subtitles, Phase 5).

**Khảo sát trước khi code phát hiện**: vùng làm mờ che watermark gốc (`BlurRegionLayer`) và vị trí phụ đề kéo-thả (`OverlayLayer` + `box_width`) đã làm từ trước (phần "Che logo/phụ đề gốc" ở trên) — chỉ thiếu 2 việc thật sự: (1) track `image` (logo/watermark) có đủ ở backend nhưng **chưa có lớp kéo-thả ở frontend** (chỉ đặt được vị trí mặc định cứng), và (2) **chưa chọn được font/màu/đậm** ở cả 2 luồng (drawtext hard-code `fontcolor=white` + font hệ thống, burn_subtitles không có `FontName`/màu).

### Font đóng gói sẵn (`font_service.py`)
Tải 4 family từ Google Fonts (giấy phép OFL) — **Be Vietnam Pro, Barlow, Fira Sans, Anton** — mỗi family bản Regular + Bold (riêng Anton chỉ có 1 file, đã đủ đậm sẵn theo thiết kế). Chỉ chọn family có **subset "vietnamese" chính thức** trên Google Fonts (kiểm tra `METADATA.pb` từng family) — nhiều font Latin cơ bản (vd Poppins, PT Sans) thiếu hẳn dấu tiếng Việt dù trông như hỗ trợ Unicode, chọn nhầm sẽ ra chữ mất dấu mà không báo lỗi gì.

Đóng gói **cùng mã nguồn** (`app/resources/fonts/`), không dò font hệ thống — quan trọng cho bản đóng gói desktop (Phase 12): máy user cài Windows sạch có thể thiếu font. `config.py` thêm `resource_dir()` (đọc từ `sys._MEIPASS` khi đã đóng gói PyInstaller, từ `BACKEND_DIR` khi chạy dev); `viedub-backend.spec` thêm `datas=[('app/resources/fonts', ...)]` — **chưa build lại + chạy thử bản đóng gói thật để xác nhận PyInstaller gom đúng** (ngoài phạm vi phiên này).

`GET /api/fonts` (danh sách), `GET /api/fonts/{id}/file` (tải file .ttf, dùng cho `@font-face` xem trước — hiện **chưa** dùng ở frontend, chỉ mới có endpoint).

### Watermark/logo kéo-thả
`ImageLayer` mới (song song `OverlayLayer`/`BlurRegionLayer`): kéo di chuyển x/y (toạ độ tâm), kéo góc dưới-phải đổi `width`. Không cần sửa backend — `render_timeline` track `image` đã hỗ trợ đủ từ Phase 9. `ClipInspector` thêm case `image` (opacity) và `blur` (mode blur/pixelate, strength) — trước đó 2 loại clip này **không sửa lại được qua UI** sau khi thêm (chỉ đặt được lúc tạo).

### Font/màu/đậm cho phụ đề — cả 2 luồng
- **Timeline Editor (track overlay)**: `TimelineClip` thêm `font_family`/`font_color`/`bold`. `render_timeline` resolve fontfile qua `font_service`, `fontcolor=0x{hex}` thay cố định trắng. Áp **theo cả track** (giống `box_width` đã có) chứ không theo từng câu — control gộp vào `SubtitleBoxPanel` (dropdown font + color picker + checkbox đậm), tránh mỗi câu 1 kiểu.
- **burn_subtitles (Phase 5)**: thêm `font_family`/`font_color`/`bold`. `force_style` thêm `FontName=`/`PrimaryColour=`/`Bold=`; `PrimaryColour` dùng định dạng ASS `&HAABBGGRR&` (đảo BGR, alpha 00=đục) — hàm `_hex_to_ass_color()` convert, có test riêng vì thứ tự byte rất dễ đảo nhầm (giống bẫy `Alignment` SSA v4 đã gặp trước đó). Dùng `fontsdir=` trỏ vào thư mục font đã đóng gói để libass tìm đúng font mà **không** phụ thuộc fontconfig hệ thống — né đúng lỗi "Fontconfig error" đã gặp với `drawtext` trước đây. UI: 3 tuỳ chọn mới (font/màu/đậm) thêm vào step "Ghép phụ đề vào video" ở `video-detail.tsx`, dùng chung schema `StepOption` có sẵn (thêm type `'color'`).

### Test
- `test_font_service.py` (13 test): catalog, fallback khi id lạ/rỗng, mọi file đăng ký thật sự tồn tại trên đĩa (bắt lỗi gõ nhầm tên file).
- `test_ffmpeg.py` (+21 test sau vòng review): render thật qua từng font trong 4 font (không crash), `font_color` đổi màu chữ thật — đo bằng `signalstats` SATAVG (chữ trắng SATAVG~0, chữ đỏ SATAVG tăng rõ rệt) thay vì OCR; `_hex_to_ass_color`/`_validate_hex_color` test riêng (pure function, không cần ffmpeg), gồm ca ký tự không phải hex (`'0:0000'`) phải bị chặn.
- `ImageLayer.test.tsx` (5 test, browser thật qua `vitest-browser-react`): vị trí đúng tỉ lệ, kéo đổi x/y, kéo góc đổi width, ẩn/hiện theo mốc thời gian.
- `store.test.ts` (+2 test): `updateTrackClips` áp patch cho cả track trong đúng 1 bước lịch sử (không phải N bước).
- 461 test backend, 197 test frontend, `ruff check`/`tsc -b`/`eslint` sạch (không tính 2 lỗi có sẵn từ trước, không liên quan: `pipeline.py` B008 Depends-in-default và `editor/index.tsx` exhaustive-deps).

### Vòng review + verify UI thật (2026-09-21, cùng phiên)
Chạy `/code-review medium` (5 agent song song), verify từng phát hiện bằng code/ffmpeg thật thay vì tin theo lời agent:
- **Sửa thật (2 bug + 1 tối ưu)**: (1) `font_color` chỉ kiểm tra độ dài 6 ký tự, không kiểm tra có phải hex hay không — chuỗi như `'0:0000'` lọt qua rồi phá cú pháp filter ffmpeg (dấu `:` là delimiter option); thêm `_validate_hex_color()` dùng regex, áp cho cả `burn_subtitles` lẫn `render_timeline` overlay. (2) `SubtitleBoxPanel.setStyle`/`setBoxWidth` gọi `updateClip` lặp cho từng câu — mỗi lần gọi đẩy 1 bước vào lịch sử undo (đọc code `store.ts` xác nhận), đổi màu track 50 câu thành 50 bước undo cho 1 thay đổi khái niệm là 1 bước; thêm action `updateTrackClips` áp patch cho cả track trong đúng 1 bước. (3) `useQuery(getFonts)` thêm `staleTime: Infinity` — danh sách font tĩnh, không cần refetch mỗi lần mở editor.
- **Verify rồi bác bỏ 1 claim**: agent báo `force_style Bold=1` sai chuẩn ASS/SSA (chỉ `Bold=-1` mới đúng chuẩn). Tự render thật bằng ffmpeg (`Bold=0/1/-1`, đo cả file size lẫn `signalstats` YAVG): `Bold=1` và `Bold=-1` ra **ảnh giống hệt byte-for-byte** (YAVG=40.64 cả hai), khác hẳn `Bold=0` (YAVG=29.08) — claim sai trên bản ffmpeg/libass đang dùng, **không sửa**.
- **Cân nhắc rồi bỏ qua có chủ đích**: vài phát hiện về trùng lặp (danh sách font hard-code ở `video-detail.tsx` STEPS trong khi `SubtitleBoxPanel` lấy động qua API; 3 component kéo-thả `OverlayLayer`/`BlurRegionLayer`/`ImageLayer` lặp lại cùng 1 pattern pointer-drag) — chấp nhận đánh đổi, khớp quy ước "3 dòng lặp lại còn hơn abstraction sớm", không phải bug.

**Verify qua Playwright thật (browser thật, không phải test suite)**: tạo video test tổng hợp bằng ffmpeg (1 video ngang 640×360, 1 video dọc 360×640) + insert thẳng vào DB dev, chạy qua UI thật:
- Kéo watermark trên canvas → lưu đúng toạ độ mới vào `timeline_json` → **render ra file thật bằng ffmpeg**, logo đúng vị trí.
- Đổi font/màu/đậm phụ đề trong Timeline Editor → lưu đúng vào track overlay → render ra file, đo `SATAVG` xác nhận đúng màu đã chọn.
- Đổi font/màu/đậm trong luồng "Ghép phụ đề vào video" (burn_subtitles) → chạy qua UI thật → `SATAVG≈92` xác nhận màu đỏ `#ff2200` đã áp đúng.
- `ClipInspector` hiện đúng field mới cho `image` (opacity) và cho phép chọn clip qua Timeline.

### Ghi chú phát sinh
- **Không thể verify family name thật trong file .ttf** bằng công cụ có sẵn (`fontTools` không có trong venv, không muốn thêm dependency chỉ để đọc tên) — tin vào quy ước đặt tên chuẩn của Google Fonts (family name khớp đúng tên hiển thị: "Be Vietnam Pro", "Barlow", "Fira Sans", "Anton"). Nếu sau này đổi bộ font, nhớ double-check field `family_name` khớp tên thật trong file, không phải suy đoán.
- **`GET /api/fonts/{id}/file` (xem trước bằng `@font-face`) chưa được dùng ở frontend** — mới có endpoint, dropdown chọn font hiện chỉ hiện tên chữ bằng font hệ thống trình duyệt, chưa preview đúng font thật. Để dành nếu cần UX tốt hơn sau này.

## Bố cục lại: tận dụng diện tích cho cả video dọc lẫn ngang (2026-09-21, cùng phiên)

**Vấn đề bạn phát hiện lúc xem UI thật**: khung xem trước cố định `max-w-md` (448px) dù màn hình rộng hơn nhiều, và mọi panel công cụ (thêm logo/nhạc nền, kiểu chữ phụ đề, chi tiết clip) xếp dọc MỘT cột phía dưới khung preview — phải cuộn qua hết preview mới chạm tới.

**Sửa bố cục** (`features/editor/index.tsx`): 2 cột từ màn hình rộng (`xl:grid-cols-[minmax(0,1fr)_22rem]`) — khung xem trước bên trái, panel công cụ (`AssetPanel`, `SubtitleBoxPanel`, `ClipInspector`) bên phải dạng sidebar `sticky`. `ClipInspector` dời từ dưới Timeline lên sidebar này — chọn clip ở Timeline (dưới cùng) vẫn thấy Inspector cập nhật ngay bên cạnh, không cần cuộn lên/xuống.

**Khung preview theo đúng tỉ lệ khung hình thật** — bỏ hẳn `max-w-md`, đo `videoDims` (đã có sẵn từ `onLoadedMetadata`) để tính `aspect-ratio` động. **2 lần thử sai trước khi ra công thức đúng, cả 2 đều tự phát hiện bằng cách đo trên browser thật với video dọc + video ngang** (không phải chỉ nhìn code):
1. `width:100% + aspect-ratio + max-height:70vh` trên block thường: height bị `max-height` cắt xuống nhưng width KHÔNG co lại theo — video dọc bị kẹp đen 2 bên như letterbox thay vì thu nhỏ vừa khung.
2. Bọc bằng `flex + justify-center` cho box aspect-ratio trở thành flex-item: video dọc đúng, nhưng video NGANG lại co về đúng kích thước gốc (640×360) thay vì lấp đầy cột rộng — vì không còn gì ép nó lớn lên khi height không chạm mức 70vh.
3. **Công thức cuối cùng, đúng cả 2 chiều**: `width: min(100%, calc(70vh * ratio))` (không cần flex wrapper, không cần đo JS) — cạnh nào hẹp hơn giữa "vừa hết bề rộng cột" và "vừa hết chiều cao 70vh quy theo tỉ lệ" thắng, rồi CSS `aspect-ratio` tự suy chiều còn lại từ `width` đã chắc chắn (chiều suy ngược, từ height sang width, thì CSS không hỗ trợ tốt trên block box — đây là gốc của lỗi #1). Verify bằng browser thật: video ngang 640×360 → box 830×467 (lấp đầy cột); video dọc 360×640 → box 368×655 (≈70vh chiều cao, không letterbox).

**Không cần code mới cho việc này** — không đổi API, không đổi test hiện có (bố cục CSS thuần, không có test tự động nào phủ layout — verify hoàn toàn bằng đo `getBoundingClientRect()` qua Playwright thật trên cả 2 tỉ lệ khung hình).

**Thu gọn header video khi ở tab "Dựng video"** (`features/videos/video-detail.tsx`, phát sinh ngay khi bạn xem lại layout mới): khối ảnh bìa + tiêu đề lớn + badge trạng thái/tác giả/thời lượng/link nguồn vốn hiện **cố định** trên mọi tab — dư thừa ở tab Dựng video vì khung preview bên trong đã hiện video rồi, lại choán thêm khoảng dọc ngay phía trên. Đổi `Tabs` từ uncontrolled (`defaultValue`) sang controlled (`value`/`onValueChange`, state `activeTab`), khi `activeTab === 'editor'` chỉ hiện 1 dòng tiêu đề gọn, các tab khác (Xử lý/Phụ đề/Giọng đọc) giữ nguyên khối đầy đủ vì vẫn cần ảnh bìa/badge để định hướng. Verify qua Playwright thật: chuyển qua lại giữa tab Xử lý ↔ Dựng video, khối header ẩn/hiện đúng theo tab.
