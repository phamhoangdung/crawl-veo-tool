# Phase 2: AI Pipeline MVP (1 provider)

Trạng thái: **Xong** — verify end-to-end bằng video thật (search → download → transcribe → translate → dub → mux), có UI thao tác theo từng bước.

## Mục tiêu
Từ 1 video đã tải (Phase 1), chạy hết pipeline: transcribe → dịch → TTS → mux, ra video lồng tiếng cơ bản. Chưa tách nhạc nền, chưa phụ đề — mục tiêu là có 1 đường ống chạy được đầu-cuối với 1 provider.

## Phạm vi
**Trong phạm vi:** `faster-whisper` transcribe, 1 provider dịch, 1 provider TTS, mux bằng ffmpeg (thay toàn bộ audio track, chưa giữ nhạc nền gốc), chế độ nhập/sửa kịch bản dịch thủ công thay auto-translate.

**Ngoài phạm vi:** đa provider, tách nhạc nền, phụ đề, Douyin.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [x] Provider dịch MVP: **fallback OpenAI ↔ Google Translate free** (quyết định của bạn: ưu tiên key trả phí nếu cấu hình + hoạt động, mặc định free). OpenAI dùng raw httpx call tới chat completions, không thêm SDK.
- [x] Provider TTS MVP: **fallback ElevenLabs ↔ Edge-TTS free**, cùng logic ưu tiên.
- [x] Cài `faster-whisper` (model `small`, CPU, `compute_type=int8`) — chạy tốt trên CPU, không cần GPU cho MVP.
- [x] Video test: dùng chính video tải qua Phase 1 (bvid `BV1sQZ7Y5EZa`, video hướng dẫn nấu ăn 141s, xác nhận nội dung là lời nói thật không phải nhạc trước khi test dịch/lồng tiếng).

## Việc cần làm
- [x] `app/adapters/translate/google.py` (free, endpoint không chính thức translate.googleapis.com) + `app/adapters/translate/openai.py`.
- [x] `app/adapters/tts/edge.py` (giọng `vi-VN-HoaiMyNeural`) + `app/adapters/tts/elevenlabs.py`.
- [x] `app/services/translate_service.py` + `tts_service.py` — logic fallback: thử provider trả phí nếu có key, lỗi thì tự chuyển free, không cần người dùng can thiệp.
- [x] `app/services/transcribe_service.py` — faster-whisper, model cache module-level (`lru_cache`) để không load lại mỗi request.
- [x] `app/services/dubbing_service.py` — orchestrate transcribe/translate/dub, cập nhật state machine (`TRANSCRIBING → TRANSLATING → DUBBING → MUXING → DONE`, có `FAILED_*` riêng từng bước).
- [x] `app/api/pipeline.py`: `POST /api/videos/{id}/download`, `/transcribe`, `/translate`, `PUT /transcript` (sửa tay), `POST /dub`, `GET /api/videos/{id}` (xem chi tiết + transcript).
- [x] `app/api/api_keys.py` + `app/services/api_key_service.py`: `GET/PUT /api/api-keys` — module quản lý key phát sinh ngay từ Phase 2 vì logic fallback cần biết key nào đã cấu hình (ban đầu dự kiến làm ở Phase 3, đẩy lên sớm hơn).
- [x] Frontend: trang `/api-keys` (nhập/lưu key theo provider, hiển thị masked key đã lưu) + nút hành động theo từng bước ngay trong bảng kết quả ở trang `/crawl` (Tải video → Tách lời thoại → Dịch → Lồng tiếng), tự cập nhật trạng thái sau mỗi bước.
- [ ] Trang xem/sửa transcript trực tiếp trên UI (hiện chỉ có API `PUT /transcript` hoạt động, chưa có form sửa trên giao diện) — để làm khi cần, backend đã sẵn sàng.
- [ ] Batch queue qua `ProcessPoolExecutor` — chưa làm, mỗi action hiện chạy đồng bộ trong request; đủ dùng khi xử lý từng video một, cần làm khi muốn chạy nhiều video song song (dời sang cùng lúc với Phase 6 hoặc khi thực sự cần).

## Tiêu chí hoàn thành (Definition of Done)
- [x] Chạy 1 video mẫu hết pipeline, ra video có giọng đọc mới — verify qua API thật: tải (BV1sQZ7Y5EZa, 141s) → transcribe (105 đoạn, faster-whisper) → translate (Google Translate free, do chưa cấu hình OpenAI key) → dub (Edge-TTS, giọng `vi-VN-HoaiMyNeural`) → mux → `dubbed.mp4` verify bằng ffprobe: video h264 + audio AAC, thời lượng khớp (~140.5s cả 2 track).
- [x] Sửa transcript/bản dịch thủ công trước khi render — `PUT /api/videos/{id}/transcript` nhận list segment đã sửa, ghi đè `transcript_json`, không bị bước dịch tự động ghi đè lại (chỉ `/translate` mới auto-dịch, `PUT` là thao tác riêng).
- [~] "Nghe hiểu được nội dung đã dịch, đối chiếu bằng tai" — chưa tự nghe kiểm tra bằng tai (không có khả năng nghe trực tiếp); đã verify kỹ thuật (audio track hợp lệ, đúng thời lượng, không lỗi khi tạo). Khuyến nghị bạn tự nghe thử `backend/storage/4/59/dubbed.mp4` để xác nhận chất lượng thực tế.

## Ghi chú phát sinh trong lúc làm
- **Chọn video test bị dính nhạc 2 lần liên tiếp**: 2 video đầu tiên chọn ngẫu nhiên từ kết quả search hoá ra là video nhạc (lời bài hát), không phải nói chuyện/vlog như tưởng — đã dừng lại, không dịch/lồng tiếng nội dung đó (tránh xử lý lại nội dung có bản quyền), chuyển sang tìm video hướng dẫn nấu ăn (nội dung nói thật, xác nhận qua transcript trước khi tiếp tục). Bài học: trước khi chạy full pipeline trên 1 video thật, nên xem qua vài dòng transcript đầu để chắc là nội dung nói chuyện, không phải nhạc — timing đều đặn theo nhịp + nội dung thơ mộng/trừu tượng là dấu hiệu của nhạc.
- **Bug đã sửa**: `x/web-interface/view` (endpoint lấy metadata video chuẩn) bị Bilibili chặn 412 (risk control) kể cả khi có cookie `buvid3`. Chuyển sang dùng `x/player/pagelist` để lấy `cid` — endpoint này ít bị chặn hơn, đủ dùng cho video 1 phần.
- **Bug đã sửa**: `edge-tts` thỉnh thoảng lỗi `NoAudioReceived` (vấn đề đã biết của thư viện, không phải do input sai) khi gọi hàng loạt (~105 lần liên tiếp cho 1 video). Đã thêm retry 3 lần (`tts_service.TtsFailedError`) và bỏ qua đoạn nếu vẫn lỗi (để khoảng lặng thay vì crash cả video) thay vì để 1 đoạn lỗi làm hỏng toàn bộ job.
- **Bug đã sửa**: `Job`/`Video` thiếu `relationship()` hai chiều đã sửa ở Phase 1 — nhắc lại vì lần này thêm cột mới (`dubbed_path`, `transcript_json`) cũng phải nhớ xoá DB cũ (`storage/app.db`) để SQLAlchemy tạo lại schema, vì MVP chưa dùng Alembic.
- Dịch qua Google Translate free gọi **tuần tự từng câu** (không batch), với video ~105 câu mất khoảng 1-2 phút — chấp nhận được cho MVP nhưng sẽ chậm với video dài; có thể cải thiện bằng cách gộp nhiều câu vào 1 request khi cần (Phase sau).
- Module quản lý API key (dự kiến ban đầu ở Phase 3) đã làm sớm ở Phase 2 vì logic fallback ưu tiên-key-trả-phí cần nó ngay — Phase 3 giờ chỉ cần thêm UI/adapter cho provider mới, không cần làm lại phần lưu trữ key.

## Bug: dịch báo "Hoàn tất" nhưng không lưu gì (phiên 2026-09-07)

**Hiện tượng**: tác vụ dịch chạy hết 32/32 câu, progress báo Hoàn tất, nhưng `translated_text` trong DB vẫn rỗng cả 32 câu → nút "Lồng tiếng" tiếp tục bị khoá với lý do "Cần dịch phụ đề trước".

**Nguyên nhân 1 — SQLAlchemy không theo dõi thay đổi bên trong cột JSON.** Code cũ sửa tại chỗ:
```python
for segment in segments:            # segments LÀ chính video.transcript_json
    segment["translated_text"] = ...
video.transcript_json = segments    # gán lại cùng object → không "dirty" → commit không ghi
```
Sửa: dựng **list mới** (`{**segment, "translated_text": ...}`) rồi gán. Đây là bẫy chung của `mapped_column(JSON)` — mọi chỗ sửa cột JSON phải tạo object mới, hoặc dùng `MutableList`/`flag_modified`. Các chỗ khác trong repo đều đã gán list mới nên chỉ `run_translate` bị.

**Nguyên nhân 2 — thiếu trạng thái "đã xong" cho từng bước.** `run_transcribe`/`run_translate` đặt status `TRANSCRIBING`/`TRANSLATING` rồi **không bao giờ đổi khi hoàn tất**, nên video kẹt mãi ở trạng thái "đang làm". Đã thêm `TRANSCRIBED` và `TRANSLATED` vào `VideoStatus` và đặt sau khi commit thành công.

**Verify thật**: chạy lại dịch → 32/32 câu lưu vào DB (`有活就干没活就炫` → `Nếu bạn có công việc, hãy làm nó...`), status `TRANSLATED`.

## Edge-TTS "No audio was received" — nguyên nhân thật (phiên 2026-09-07)

Comment cũ trong `tts_service.py` ghi lỗi này là "tạm thời của thư viện, không phải do input sai" — **sai**. Đo thật với edge-tts 7.2.8, giọng `vi-VN-HoaiMyNeural`:

| Input | Kết quả |
|---|---|
| `'Xin chào, đây là thử nghiệm.'` | OK (16992 bytes) |
| `''` / `'   '` | OK (0 bytes, không lỗi) |
| `'...'` | **NoAudioReceived** |
| `'炫饭'` (chữ Hán, giọng tiếng Việt) | **NoAudioReceived** |

Vậy lỗi xảy ra khi **văn bản không có nội dung đọc được cho ngôn ngữ của giọng** — retry 3 lần là vô ích.

**Nguyên nhân gốc trong luồng dub**: `dubbing_service` fallback `segment.get("translated_text") or segment.get("text")` — khi bản dịch rỗng (do bug SQLAlchemy JSON ở mục trên), nó lấy **lời gốc tiếng Trung** đưa cho giọng tiếng Việt đọc → lỗi ở mọi câu.

**Đã sửa**:
- `dubbing_service`: **chỉ dùng `translated_text`**, bỏ fallback về lời gốc. Câu chưa dịch thì bỏ qua (im lặng ở đoạn đó) thay vì tạo tiếng Việt đọc chữ Hán.
- `tts_service._has_speakable_content()`: chặn trước khi gọi Edge-TTS, báo lỗi ngay thay vì retry 3 lần. Regex `[^\W_]` nên chữ tiếng Việt có dấu vẫn nhận đúng.
- Log lỗi kèm 60 ký tự đầu của văn bản để truy nguyên nhanh.

Giọng khả dụng (verify qua `edge_tts.list_voices()`): `vi-VN-HoaiMyNeural` (nữ), `vi-VN-NamMinhNeural` (nam).
