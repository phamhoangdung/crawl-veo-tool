# Tối ưu hiệu năng, luồng xử lý & tốc độ — phân tích + phương án

Trạng thái: **P0 + P1 + P2 đã code xong** (2026-09-20) — 430 test backend pass, ruff sạch trên toàn bộ file đã sửa. P3 vẫn để dành như đề xuất ban đầu (không cấp thiết).

## Bối cảnh

Bạn yêu cầu refactor + tối ưu hiệu năng/luồng/tốc độ cho pipeline xử lý video, ưu tiên pipeline trước rồi tới hạ tầng host nhiều user (Phase 18). Trước khi đề xuất bất kỳ thay đổi nào, đã cho agent đọc thật toàn bộ `backend/app` để lấy số liệu/hành vi thật thay vì đoán — phần "Hiện trạng" dưới đây là kết quả khảo sát đó, kèm `file:line` để tự kiểm tra lại.

**Phát hiện quan trọng nhất, ảnh hưởng trực tiếp tới Phase 18**: server hiện tại là **1 process, 1 event loop duy nhất** (`backend/app/entrypoint.py:17`, `uvicorn.run(..., reload=False)` không có `workers=`). Nhiều đoạn code gọi thẳng ffmpeg/Demucs (I/O đồng bộ, chặn) **ngay trong 1 coroutine `async def` đang chạy trên event loop chính** — nghĩa là khi 1 video đang lồng tiếng, **toàn bộ server treo với mọi user khác** (không request nào khác xử lý được, kể cả health check hay stream tiến độ SSE) cho đến khi xong. Với 1 user dùng cá nhân hiện tại việc này vô hại (không có "user khác" để bị ảnh hưởng), nhưng đây là **rào cản cứng phải sửa trước khi host multi-tenant (Phase 18)** — không phải tối ưu tốc độ đơn thuần, mà là bug đúng nghĩa sẽ lộ ra ngay khi có ≥2 user dùng cùng lúc.

## Hiện trạng (khảo sát thật, có file:line)

### 1. Event loop bị chặn — vấn đề nghiêm trọng nhất

- `dubbing_service.run_dub_and_mux` (dubbing_service.py:154, `async def`, chạy trực tiếp trên event loop chính khi được queue làm background task) gọi **đồng bộ, không `await`, không `to_thread`**: `ffmpeg.extract_audio` (dòng 217), `audio_chunk_service.separate_vocals` — tức Demucs (dòng 232-237), `ffmpeg.mix_audio_tracks` (dòng 242), `ffmpeg.replace_audio_track` (dòng 252). Mỗi lệnh này có thể mất vài chục giây tới vài phút với video dài — suốt thời gian đó **không request nào khác của server được xử lý**.
- Batch job (`batch_service.execute_batch`) còn nặng hơn: `run_step` (pipeline.py:331, `async def`) cho bước `"transcribe"` gọi thẳng `dubbing_service.run_transcribe` (pipeline.py:356) — khác với route `/transcribe` đơn lẻ (vô tình an toàn vì hàm queue là `def` thường, Starlette tự đẩy sang threadpool), batch gọi trực tiếp trong `async def` nên **treo cả server suốt thời gian faster-whisper chạy**. Tương tự với bước `"dub"` (dòng 360) và `"burn"` (dòng 362).
- `POST /{video_id}/burn-subtitles` (pipeline.py:313) không chạy nền — request đứng chờ suốt thời gian ffmpeg re-encode + chiếm 1 thread trong threadpool giới hạn của Starlette.

### 2. ffmpeg: mỗi lệnh là 1 process con mới, luôn đồng bộ

`backend/app/adapters/ffmpeg.py` dùng `subprocess.run(...)` cho mọi hàm — không có async subprocess. Một video ≤600s đi hết download→transcribe→diarize→dub→burn tốn khoảng **8+N lần spawn ffmpeg/ffprobe** (N = số đoạn TTS cần time-stretch). Không phải vấn đề cấp bách (mỗi process ngắn), nhưng cộng dồn với việc chặn event loop ở mục 1 thì mỗi lần spawn là 1 lần "đóng băng" thêm.

### 3. Model loading

- faster-whisper: cache đúng qua `@lru_cache` (transcribe_service.py:7-10) — tốt, không cần sửa.
- SpeechBrain (diarization, Phase 19): cache đúng qua singleton module-level (diarization_adapter.py:15, 31-42) — tốt, không cần sửa.
- **Demucs: KHÔNG cache** — mỗi lần gọi là 1 process Python mới (`demucs.py:14-23`, `subprocess.run([sys.executable, "-m", "demucs", ...])`), nghĩa là **load lại model từ đĩa mỗi lần**. Với video dài (>600s, chia chunk — `audio_chunk_service.py:25`), Demucs bị gọi **1 lần mỗi chunk trong vòng lặp** (audio_chunk_service.py:104) → trả phí load model nhân lên theo số chunk.
- Translate/TTS: **không tái dùng HTTP client** — `translate_service.translate_text` (dòng 57) và `tts_service.synthesize_speech` (dòng 95) mỗi lần gọi đều `httpx.AsyncClient(...)` mới. Với `_MAX_CONCURRENT_SEGMENTS = 8`, 1 video 32 câu mở/đóng **32 client riêng** (32 lần bắt tay TLS/connection pool) cho dịch, thêm 32 lần nữa cho TTS — lãng phí rõ ràng dù không chặn event loop (đã async đúng).

### 4. Song song hoá

- Trong 1 video: các bước bắt buộc tuần tự qua `VideoStatus` (đúng, cần thiết — output bước sau phụ thuộc bước trước). Trong nội bộ bước dịch/TTS: đã song song đúng, giới hạn `_MAX_CONCURRENT_SEGMENTS = 8` (dubbing_service.py:29), có số đo thật (32 câu: dịch 8s→2s, TTS 54s→5s — dubbing_service.py:90,174).
- Giữa nhiều video (batch): `DEFAULT_CONCURRENCY = 1` (batch_service.py:19), có lý do rõ ràng ghi trong comment ("whisper/demucs ăn hết CPU, chạy song song chỉ làm chậm cả 2") — **đây là quyết định đúng cho máy đơn hiện tại, KHÔNG phải bug**, giữ nguyên. Chỉ cần xem lại khi có hạ tầng nhiều worker/nhiều máy thật (Phase 18).
- Chỉ 1 batch job chạy được cùng lúc toàn hệ thống (`_current`/`_lock` singleton, batch_service.py:56-60) — hợp lý với model 1 process hiện tại.

### 5. I/O thừa

- **`original_audio.wav` bị trích xuất 2 lần** nếu chạy diarize trước dub (luồng bình thường): `run_diarize` có check tồn tại trước khi extract (dubbing_service.py:71-74, đúng), nhưng `run_dub_and_mux` gọi `ffmpeg.extract_audio` **vô điều kiện, không check** (dòng 216-217) — ghi đè lại đúng file diarize vừa tạo. Đây là chỗ đơn giản nhất để sửa, cùng pattern có sẵn.
- File tạm theo từng đoạn (`tts_segments/segment_*_raw.mp3`, `*_stretched.mp3`, và với video dài: `_chunks/*.wav`, `out*/htdemucs/.../vocals.wav`) **không bao giờ được dọn** sau khi xong — chỉ có `storage_cleanup_service.cleanup_old_job_folders` xoá cả thư mục job sau 30 ngày (storage_cleanup_service.py:19-41), không có dọn theo từng bước/từng video ngay sau khi hoàn tất.

### 6. Database

- N+1 query: `crawl_service.create_job_from_selection` (dòng 213-218) và `append_videos_to_job` (dòng 256-263) query từng item 1 trong vòng lặp — trong khi hàm chị em `create_job_from_search` trong cùng file đã làm đúng bằng 1 query `.in_(bvids)` (dòng 127-135). Rõ ràng là thiếu sót chứ không phải cố ý.
- Bảng `videos` không có index cho các cột hay lọc: `dubbed_path`, `local_path`, `user_id` (dùng ở batch_service.py:194, library_service.py:11-12, file_manager_service.py:55-56,194) — full scan, chưa vấn đề với dữ liệu ít nhưng sẽ chậm dần khi nhiều user/nhiều video (Phase 18).

## Phương án đề xuất — chia theo mức ưu tiên

### P0 — Bắt buộc trước khi host multi-tenant (Phase 18), nên làm cả khi vẫn dùng cá nhân vì đỡ "đứng hình" UI lúc xử lý video dài

**Vấn đề**: event loop bị chặn (mục 1).

**Đã làm** (2026-09-20):
- [x] `run_dub_and_mux`: bọc `extract_audio`, `separate_vocals` (Demucs), 2 `voice_timeline.export` (pydub, cũng shell ra ffmpeg), `mix_audio_tracks`, `replace_audio_track` bằng `await asyncio.to_thread(...)`.
- [x] `download_service.download_bilibili_video`: bọc `ffmpeg.merge_video_audio` tương tự (phát hiện thêm khi rà lại nguyên tắc "mọi lệnh chặn", không chỉ 4 lệnh liệt kê ban đầu trong `run_dub_and_mux`).
- [x] `run_step` (batch): bọc `dubbing_service.run_transcribe` và nhánh `"burn"` bằng `asyncio.to_thread`. Nhánh `"dub"` tự động an toàn vì gọi `run_dub_and_mux` đã sửa ở trên.
- [x] `burn_subtitles` route: đổi thành chạy nền qua `BackgroundTasks` (thêm `_run_burn`, kind `"burn"` đã có sẵn trong `TaskKind`) — không giữ request mở, nhất quán với transcribe/translate/dub/diarize. Đổi hành vi: lỗi `position` không hợp lệ giờ báo qua `error_message` thay vì HTTP 422 ngay lập tức (chấp nhận đánh đổi này để nhất quán, xem docstring route).
- [x] `_run_transcribe`/`_run_diarize` (single-video route, không phải batch): **không cần sửa** — đã an toàn đúng cách nhờ là hàm `def` thường, Starlette tự chạy qua threadpool khi queue bằng `BackgroundTasks` (đây là hành vi CHÍNH THỨC của Starlette, không phải "vô tình" như nhận định ban đầu trong bản phân tích — chỉ sai khi hàm queue là `async def` mà bên trong vẫn gọi chặn trực tiếp, đúng như các case đã sửa ở trên).

**Vì sao chọn `asyncio.to_thread` thay vì nhảy thẳng lên Celery/Redis**: `subprocess.run` (ffmpeg/Demucs) và phần lớn compute nặng của PyTorch (faster-whisper/SpeechBrain) đều nhả GIL trong lúc chờ — chạy trong thread pool của Python đã đủ giải phóng event loop, không cần hạ tầng process/queue riêng. Rào cản thật sự cho nhiều-user-đồng-thời-xử-lý-nặng-cùng-lúc (nhiều video tranh CPU/GPU thật) vẫn cần worker pool thật — đó là P2, chưa làm.

**Không nằm trong phạm vi P0**: đổi cách batch chạy song song (`DEFAULT_CONCURRENCY=1` giữ nguyên, đúng cho máy đơn).

### P1 — Nhanh, rủi ro thấp, lợi ích tốc độ rõ

1. [x] **Tái dùng `httpx.AsyncClient`** cho `translate_service` (`_get_client()`, timeout 60s dùng chung cho cả `translate_text`/`complete_text`) và `tts_service` (`_get_client()` riêng, timeout 60s) — singleton module-level, không đóng tường minh (xem docstring từng hàm).
2. [x] **Bỏ trích xuất `original_audio.wav` thừa**: thêm check tồn tại trong `run_dub_and_mux`, cùng pattern `run_diarize` đã có.
3. [x] **Sửa N+1 query** ở `create_job_from_selection`/`append_videos_to_job` — đổi sang 1 query `.in_(...)`, cùng pattern `create_bilibili_crawl_job`.
4. [x] **Dọn file tạm theo từng video**:
   - `_synthesize_segment_matched_duration` (dubbing_service.py): xoá `segment_*_raw.mp3`/`segment_*_stretched.mp3` ngay sau khi đã nạp vào bộ nhớ (`AudioSegment`), ở cả 3 nhánh return.
   - `audio_chunk_service.separate_vocals` (video dài, có chunk): `shutil.rmtree(work_dir, ignore_errors=True)` sau khi `concat_audio` xong — xoá `_chunks/part*.wav` + `out*/htdemucs/...`.
   - **Cố ý KHÔNG xoá** `original_audio.wav`, `voice_timeline.mp3`, và thư mục `demucs_out/htdemucs/<stem>/` (stem cuối, không phải `_chunks`) — `timeline_service.py:204-205` (Phase 13, Timeline Editor) đọc trực tiếp các đường dẫn này để lấy waveform/audio stems, xoá sẽ làm hỏng tính năng đó mà không báo lỗi rõ ràng.

### P2 — Worker pool thật (đã code 2026-09-20, sớm hơn dự định — xem Ghi chú)

**Quyết định kỹ thuật**: `ProcessPoolExecutor` (stdlib), KHÔNG dùng Celery/Redis. Lý do: `docs/phases/phase-18-auth-license-hosting.md` đã ghi rõ "Ngoài phạm vi: Auto-scaling/multi-server (1 server đơn là đủ cho giai đoạn đầu)" — lợi ích chính của Celery (phân tán việc ra nhiều máy) không cần cho mục tiêu 1 server; thêm Redis chỉ thêm 1 service phải vận hành/theo dõi mà chưa đúng lúc cần. `ProcessPoolExecutor` đạt đúng mục tiêu thật sự cần (cách ly process, tận dụng nhiều core khi deploy server khoẻ hơn) mà không thêm hạ tầng ngoài.

**Phát hiện quan trọng khi thiết kế — thu hẹp phạm vi so với dự tính ban đầu**: ffmpeg và Demucs **không cần** đưa vào process pool — cả hai đã tự chạy dưới dạng `subprocess.run` (1 process OS riêng) từ trước, `asyncio.to_thread` ở P0 đã là giải pháp đúng và đủ (thread Python chỉ *chờ* process con đó, việc nặng vốn đã nằm ngoài process Python). Đưa các lệnh này vào `ProcessPoolExecutor` sẽ chỉ tốn thêm chi phí serialize mà không tăng cách ly gì. Chỉ 2 hàm THẬT SỰ cần: `transcribe_service.transcribe` (faster-whisper) và `diarization_adapter.assign_speakers` (SpeechBrain, Phase 19) — cả hai chạy PyTorch **trong** process Python, không qua subprocess.

**Ràng buộc quan trọng phải tôn trọng khi chọn hàm đưa vào pool**: hàm đưa vào `ProcessPoolExecutor` chạy ở 1 process con, KHÔNG chia sẻ bộ nhớ với process cha — nghĩa là KHÔNG được đụng `db: Session` (SQLAlchemy session không gửi qua process được) hay `progress_service` (dict module-level, cập nhật trong process con thì process cha không thấy). Vì vậy chỉ đưa đúng lời gọi compute thuần vào pool (`transcribe_service.transcribe(path, language)` → `list[dict]`, `diarization_adapter.assign_speakers(path, segments)` → `list[dict]`), còn `run_transcribe`/`run_diarize` (đụng DB + `progress_service`) vẫn chạy ở process chính như cũ, chỉ `.result()` chờ future.

**Đã làm**:
- [x] `app/core/worker_pool.py` (mới): `submit()`/`get_pool()`/`shutdown()`, pool size qua setting `cpu_worker_count` (mặc định 1, khớp hành vi hiện tại — tăng qua env khi deploy server nhiều core hơn, Phase 18).
- [x] `dubbing_service.run_transcribe`/`run_diarize`: gọi qua `worker_pool.submit(...).result()` thay vì gọi thẳng.
- [x] `app/main.py`: shutdown handler gọi `worker_pool.shutdown()` — không để worker process mồ côi khi tắt server.
- [x] `backend/tests/conftest.py`: fixture `autouse` fake `worker_pool.submit` chạy đồng bộ trong process test (tránh test chậm/flaky vì multiprocessing thật, và vì `monkeypatch` không xuyên được sang process con — module trong worker sẽ import bản gốc, không thấy patch).
- [x] `backend/tests/core/test_worker_pool.py` (mới, đè tên fixture để dùng pool THẬT — không qua fake): xác nhận submit chạy đúng, trả đúng kết quả, pool được tái dùng giữa các lần submit, kwargs được chuyển đúng.

**Chưa làm / để dành**: batch `DEFAULT_CONCURRENCY` vẫn giữ nguyên = 1 (không đổi — lý do RAM tranh chấp trong comment gốc vẫn đúng dù đã cách ly process, không tự ý nâng lên khi chưa có tín hiệu thật cần). Chưa verify bằng tải thật nhiều video đồng thời.

### P3 — Không cấp thiết, cân nhắc sau

- Demucs load model qua subprocess Python mới mỗi lần — có thể gọi qua Python API trực tiếp (`demucs.separate` in-process) để tránh reload, nhưng đánh đổi: mất cách ly tiến trình (Demucs lỗi/crash không còn tự cô lập khỏi server chính). Không ưu tiên vì Demucs vốn đã cache đúng theo chunk, chỉ lặp lại với video rất dài.
- Thêm index cho `videos.dubbed_path`/`local_path`/`user_id` — chỉ đáng làm khi dữ liệu đủ lớn để đo được chênh lệch thật (hiện tại ít video, chưa đáng).
- Giảm số lần spawn ffmpeg (gộp lệnh bằng `filter_complex`) — phức tạp hoá code để đổi lấy lợi ích nhỏ (mỗi process ffmpeg ngắn), không đáng đánh đổi.

## Việc cần bạn quyết định

- [x] P0 + P1 làm chung 1 phiên (2026-09-20) — xong.
- [ ] P2 (worker pool thật) để dành đúng lúc vào Phase 18 như đề xuất ban đầu — giữ nguyên, chưa làm.
- [ ] P3: vẫn bỏ qua cho tới khi có tín hiệu thật cần (nhiều video/nhiều user) — chưa làm, đúng dự định.

## Ghi chú phát sinh trong lúc làm

- **427 test backend pass**, không test nào phải viết mới cho riêng phần to_thread-wrapping (bản chất là đổi cách gọi hàm đã có, không đổi logic — không có gì mới để test ngoài "vẫn chạy đúng như cũ", đã được test hiện có phủ qua `_synthesize_segment_matched_duration`, `test_batch_service.py`...). Có sửa 2 test cũ trong `test_dubbing_service.py` đang assert file tạm **tồn tại** sau khi chạy — đổi thành assert **không tồn tại** vì đó chính là hành vi mới cố ý (dọn file tạm, mục P1.4).
- **`ruff check`/`format`**: chỉ áp dụng cho các file đã sửa trong phiên này, KHÔNG chạy toàn repo — `ruff check backend/app backend/tests` phát hiện 157 lỗi có sẵn từ trước (import order, `B008 Depends-in-defaults` trải khắp mọi route FastAPI theo đúng convention cũ của dự án, `B023` loop-variable-binding trong lambda vốn đã vậy từ trước, `ASYNC230` ở `download_service.py` không đụng tới) — đã đối chiếu kỹ từng lỗi trên các file mình sửa để phân biệt "lỗi có sẵn, không phải việc của phiên này" khỏi "lỗi do mình gây ra", chỉ fix đúng phần sau. Không dọn 157 lỗi kia — ngoài phạm vi yêu cầu, sẽ là 1 phiên dọn dẹp riêng nếu bạn muốn.
- **Phát hiện thêm ngoài 4 lệnh liệt kê ban đầu trong `run_dub_and_mux`**: 2 lệnh `voice_timeline.export(..., format="mp3")` (pydub) cũng shell ra ffmpeg ngầm bên trong, xuất audio dài cả video — đã bọc `to_thread` luôn dù bản phân tích gốc không liệt kê tên cụ thể, đúng tinh thần "mọi lệnh chặn" đã đề ra. Tương tự phát hiện `download_service.py` có 1 lệnh `ffmpeg.merge_video_audio` bị bỏ sót khỏi bản phân tích ban đầu (chỉ tập trung vào dub), đã sửa luôn.
- **Không đổi gì ở `run_diarize`/`_run_transcribe`/`_run_diarize` (route đơn lẻ)**: khảo sát kỹ lại thấy các hàm này vốn đã an toàn đúng cách (hàm `def` thường, Starlette tự threadpool khi queue bằng `BackgroundTasks` — hành vi chính thức, không phải may rủi). Bản phân tích ban đầu dùng chữ "vô tình an toàn" hơi quá — đã đính chính lại cách hiểu ở mục P0 trên.

## Phần frontend (2026-09-22) — rà soát tái sử dụng component + hiệu năng render

Khác phạm vi ở trên (backend pipeline) — phiên này khảo sát toàn bộ `frontend/src` để tìm chỗ nên gộp thành component dùng chung và chỗ re-render thừa, bằng 3 agent song song đọc thật code (không đoán). Đã làm, theo thứ tự ưu tiên:

**2 bug thật phát hiện khi khảo sát (không phải chỉ gu code):**
- **Undo/Redo trong Timeline Editor (Phase 13) bị vô hiệu hoá sau khi kéo bất kỳ thứ gì** — `editor/store.ts` cũ đẩy 1 bước lịch sử **mỗi lần `pointermove`** (60-120 lần/giây), 1 cú kéo dài tiêu hết cả 50 bước lịch sử. `flow/store.ts` (Phase 16, module dựng video AI) đã tự phát hiện và sửa đúng lỗi này trước đó (`beginGesture`/`endGesture`, gộp cả cử chỉ thành 1 bước) nhưng chưa bao giờ backport sang `editor/store.ts`. Đã áp dụng cùng pattern, verify bằng 10 test mới (kéo 15-20 lần `pointermove` chỉ tốn đúng 1 bước undo).
- **Biểu đồ chuyên mục Trending hiện sai đơn vị** ("1.5M" thay vì "1.5Tr") — `category-chart.tsx` tự viết lại `formatCompact` bằng hậu tố tiếng Anh thay vì dùng bản chung có hậu tố tiếng Việt đã có sẵn trong `./format.ts`.

**Tái sử dụng (đều đã có 2+ chỗ gọi thật, không phải suy đoán):**
- `lib/api.ts::getApiErrorMessage()` — thay 14+ chỗ tự bóc `error.response.data.detail`, trong đó 1 vài chỗ dùng cách kiểm tra yếu hơn (`'response' in error`) dễ nhận nhầm lỗi non-HTTP.
- `components/layout/app-header.tsx::AppHeader` — gộp 11 file có cùng 1 khối `<Header><Search/><TaskMonitor/>...</Header>` y hệt; **phát hiện drift thật lúc gộp**: trang Settings thiếu hẳn `<TaskMonitor />` so với 10 trang còn lại.
- `lib/format.ts` — gộp `formatDuration`/`formatBytes`/`formatTime` (8 chỗ lặp y hệt).
- `hooks/use-pointer-drag.ts::usePointerDrag` — gộp phần lifecycle pointermove/pointerup của 3 component kéo-thả trên canvas (Overlay/Blur/Image layer, Phase 13), vá luôn lỗi thiếu cleanup khi unmount giữa chừng ở 2/3 component.
- `components/video-preview-dialog.tsx::VideoPreviewDialog` — gộp popup xem nhanh (iframe nhúng + link mở ngoài) dùng chung cho lưới video Bilibili và YouTube ở trang Trending; **cố ý KHÔNG gộp phần card** (checkbox chọn, huy hiệu Hot, mutation tạo job) vì khác nhau thật giữa 2 nền tảng.
- `youtube-panel.tsx` đổi sang dùng `CoverImage` chung (có lazy-load) thay vì `<img>` thô.

**Hiệu năng render — ảo hoá danh sách phụ đề** (thêm dependency `@tanstack/react-virtual`):
- `features/videos/subtitle-editor.tsx` + `subtitle-review.tsx`: video dài (faster-whisper ra ~1 segment/vài giây) có thể ra 500-1000+ câu — trước đây dựng hết thành DOM node cùng lúc. Giờ ảo hoá + tách mỗi hàng thành component `memo()` riêng (gõ 1 ký tự không re-render toàn bộ danh sách).
- **Bẫy phát hiện khi verify bằng test browser thật, không phải lý thuyết**: `useVirtualizer` (ResizeObserver-based) đo ra **0 hàng** ở lần đo đầu tiên khi container nằm trong Radix `Dialog` (`subtitle-editor.tsx` mở qua Dialog) — dialog vẫn đang định vị lúc ResizeObserver bắn callback đầu tiên. Tự dựng 2 test tối giản (ngoài Dialog / trong Dialog) để cô lập đúng nguyên nhân trước khi sửa. Cách sửa: ép 1 lần re-render ngay sau mount (`useEffect` rỗng deps gọi 1 `setState`) để virtualizer đo lại. Áp dụng phòng ngừa cho cả `subtitle-review.tsx` dù component đó không nằm trong Dialog.
- Thu hẹp Zustand selector cho 4 component (Overlay/Blur/Image layer + SubtitleBoxPanel): trước đây `useEditorStore(s => s.operations)` khiến mọi component render lại khi BẤT KỲ track nào đổi; giờ chỉ subscribe đúng track cần. Dựa vào tính chất `mapTrack` trong store giữ nguyên reference của track không đổi (immutable update chỉ tạo object mới cho track bị sửa) nên so sánh mặc định `Object.is` của Zustand vẫn đúng, không cần `useShallow`. Verify bằng test riêng xác nhận invariant này.

**Verify:** 217 test frontend (từ 197 đầu phiên) + 464 test backend pass, `tsc`/`eslint` sạch (2 warning không tránh được do đặc thù `useVirtualizer` + React Compiler, không phải lỗi). Trang Trending verify thêm qua Playwright + API Bilibili thật (popup xem trước ra đúng iframe/link/tiêu đề).

**Cố ý không làm** (theo đúng đánh giá của agent khảo sát, tránh gộp cưỡng ép code khác nhau thật): AI-generated image chưa có bản thumbnail (cần sửa cả backend, để sau); `GenerationJobsPanel`/`SessionHistory` ở ai-studio không gộp vì nội dung hàng khác nhau thật.
