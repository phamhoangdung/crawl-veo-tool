# Phase 19: Lồng tiếng nhiều giọng — phân vai người nói (speaker diarization)

Trạng thái: **Phần lõi code xong, test pass** (2026-09-20) — backend + frontend đã viết, 431 test backend + 190 test frontend pass, ruff/eslint/tsc sạch. **Chưa verify bằng video thật** (vẫn thiếu video mẫu ≥2 người nói) và **GPU chưa thực sự chạy được** (xem Ghi chú).

## Mục tiêu
Pipeline lồng tiếng hiện tại (Phase 2) dùng 1 giọng đọc cho toàn bộ video. Phase này thêm khả năng AI tự nhận diện có nhiều người nói khác nhau trong video (vd 2 nhân vật đối thoại), tách theo từng đoạn thoại kèm nhãn "ai đang nói", rồi cho user gán mỗi vai 1 giọng đọc riêng (nam/nữ/giọng khác nhau) — lồng tiếng nghe tự nhiên hơn thay vì 1 giọng đọc hết cả video.

## Phụ thuộc
Không phụ thuộc cứng vào Phase 18 — có thể làm độc lập trên pipeline hiện tại (vẫn chạy được ở chế độ single-user). Nếu muốn giới hạn tính năng này cho gói Pro/ProMax (như đã đề cập khi lên plan chung), cần Phase 18 xong phần feature-gating (Giai đoạn B) trước khi gắn cờ giới hạn — nhưng phần kỹ thuật diarization/TTS ở phase này làm trước được, không cần chờ.

## Phạm vi

**Trong phạm vi:**
- Thêm bước diarization dựa trên **SpeechBrain (ECAPA-TDNN speaker embedding) + clustering**, KHÔNG dùng pyannote — xem "Quyết định kỹ thuật" dưới. Giữ nguyên bước transcribe Whisper hiện có (Phase 2) để lấy segment + timestamp, thêm bước riêng gắn nhãn speaker (`SPEAKER_00`, `SPEAKER_01`...) lên từng segment đó.
- Lưu speaker label theo segment trong DB.
- UI bước mới trong luồng dubbing: hiện danh sách speaker đã phát hiện (kèm vài câu thoại mẫu của mỗi speaker để user nhận ra "đây là ai"), cho user:
  - Sửa tay nếu AI gán nhầm speaker cho 1 đoạn (diarization tự động không phải lúc nào cũng đúng 100%, đặc biệt đoạn ngắn/giọng giống nhau).
  - Chọn giọng đọc (voice) riêng cho từng speaker từ danh sách giọng có sẵn theo provider, có nhãn giới tính (nam/nữ) để dễ chọn.
- `tts_service.py` mở rộng: nhận map `speaker_label -> voice_id` thay vì 1 voice chung, render riêng từng segment bằng đúng giọng, ghép lại theo timeline gốc (tái dùng cơ chế ghép theo timestamp đã có).
- Giữ nguyên tách nhạc nền (Demucs, Phase 4) — nhiều giọng chỉ thay track thoại, không đụng track nhạc nền.
- Phụ đề song ngữ (Phase 5): không đổi cấu trúc, chỉ cần đảm bảo vẫn đúng thứ tự khi segment giờ có thêm field speaker.

**Ngoài phạm vi:**
- Voice cloning để giọng lồng giống giọng gốc từng nhân vật thật (khác với chỉ chọn 1 giọng có sẵn nam/nữ) — để sau, tham khảo hướng ở `docs/free-local-models/research.md` nếu muốn làm offline, hoặc ElevenLabs voice cloning nếu online.
- Tự động đoán giới tính từ giọng gốc để gợi ý sẵn giọng dịch phù hợp — nice-to-have, để sau khi tính năng cơ bản (user tự chọn giọng cho từng speaker) đã chạy ổn.
- Diarization cho video có quá nhiều người nói xen kẽ nhanh (vd nhóm chat đông người) — MVP nhắm video 2-4 người nói rõ ràng (phổ biến với nội dung phim/clip đang crawl).

## Quyết định kỹ thuật (chốt phiên 2026-09-20 — đổi khỏi đề xuất ban đầu)

Đề xuất ban đầu là WhisperX + pyannote.audio, nhưng pyannote (từ bản 3.x) là **gated model trên Hugging Face** — không tốn tiền, nhưng bắt buộc đăng nhập HF + bấm "Agree" thủ công trên từng trang model trước khi tải được. Bạn muốn tránh hẳn bước này (ưu tiên mã nguồn mở/miễn phí, không có bước xin quyền thủ công).

**Hướng thay thế đã chọn**: dùng **SpeechBrain ECAPA-TDNN** (`speechbrain/spkrec-ecapa-voxceleb`) để trích **speaker embedding** cho từng đoạn thoại (đã có sẵn từ Whisper transcribe, Phase 2 — không cần chạy lại VAD riêng), rồi **cluster** các embedding đó (vd `AgglomerativeClustering` của scikit-learn, không cần biết trước số người nói) để gán nhãn speaker cho từng segment. Model SpeechBrain này public trên HF, tải tự động không cần đăng nhập/accept license thủ công — vẫn là mã nguồn mở, miễn phí, chỉ khác ở chỗ không có bước gate.

**Đánh đổi cần biết**: pyannote là pipeline diarization chuyên dụng (có xử lý overlap speech, VAD riêng, được huấn luyện trực tiếp cho tác vụ này) nên thường chính xác hơn. Cách SpeechBrain+clustering ở đây là ghép 2 công cụ theo hướng "đủ dùng, không cần gate" — có thể kém chính xác hơn với đoạn thoại rất ngắn hoặc nhiều người nói chồng tiếng nhau. Vì MVP nhắm video 2-4 người nói rõ ràng (không phải hội thoại nhóm đông, xem "Ngoài phạm vi"), đánh đổi này chấp nhận được. Nếu độ chính xác không đạt khi test thật, cân nhắc quay lại pyannote (chấp nhận bước gate) như phương án dự phòng — ghi chú lại đây để không quên đã có lựa chọn khác.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [x] ~~Tài khoản Hugging Face + accept model license (pyannote)~~ — không cần nữa, đã đổi sang SpeechBrain (ungated) ở trên.
- [x] **CPU hay GPU cho diarization**: chốt 2026-09-20 — máy dev đã có GPU NVIDIA dùng được, chạy GPU cho nhanh. Cần verify CUDA/driver + bản torch cài trong `backend` có support CUDA đúng khi vào phiên code (không giả định sẵn khớp).
- [ ] **Video mẫu có ít nhất 2 người nói rõ ràng, xen kẽ** (chốt 2026-09-20: chưa có, cần tự chuẩn bị) — dùng luôn tính năng crawl Bilibili (Phase 1) sẵn có để tìm 1 clip phim/kịch có ≥2 nhân vật đối thoại rõ ràng, tải về làm mẫu test.
- [ ] **Danh sách giọng nam/nữ theo từng provider đang dùng** (ElevenLabs, Edge-TTS) gắn nhãn giới tính trong config — kiểm tra provider hiện có đủ giọng cả nam lẫn nữ tiếng Việt (hoặc ngôn ngữ đích) chưa, để UI chọn giọng không bị thiếu lựa chọn. (Việc này đọc code hiện có để xác nhận, không cần bạn chuẩn bị gì thêm.)

## Kiến trúc đề xuất (cao cấp — chi tiết hoá khi vào code)
- `app/adapters/diarization_adapter.py` (mới): input là audio path đã tách thoại (output Demucs, Phase 4) + list segment đã có từ Whisper transcribe (Phase 2, có sẵn `start`/`end`/`text`); với mỗi segment cắt đoạn audio tương ứng, trích embedding bằng SpeechBrain ECAPA, cluster toàn bộ embedding (Agglomerative, không cần biết trước số speaker), trả lại list `{start, end, text, speaker_label}`.
- Model/schema: kiểm tra bảng transcript/segment hiện tại (đọc code khi vào phiên, không đoán trước ở đây) — nhiều khả năng cần thêm cột `speaker_label` vào bảng segment hiện có thay vì tạo bảng mới, giữ đúng tinh thần "3 dòng lặp lại còn hơn abstraction sớm" trong `docs/conventions.md`.
- `app/services/dubbing_service.py`: sau bước transcribe hiện có, gọi thêm diarization adapter khi user bật tính năng nhiều giọng (giữ luồng 1-giọng cũ làm mặc định/fallback cho video 1 người nói — không bắt buộc mọi video phải qua diarization).
- `app/services/tts_service.py`: đổi hàm render nhận `dict[speaker_label, voice_id]`, loop qua segment gọi TTS đúng giọng, giữ nguyên cơ chế fallback Edge-TTS/pool key đã có ở Phase 8.
- Frontend: bước mới trong luồng dubbing (`frontend/src/features/...` — theo đúng cấu trúc `pages/` hiện có) hiện danh sách speaker + dropdown chọn giọng + cho sửa gán vai từng đoạn.

## Việc cần làm
- [x] Cài `speechbrain` + `scikit-learn` + `torchaudio` — không xung đột `torch` hiện có (`2.14.0+cpu`).
- [x] `diarization_adapter.py`: cắt audio theo segment Whisper có sẵn (pydub, pad đoạn <300ms), trích embedding SpeechBrain ECAPA, cluster bằng `AgglomerativeClustering` (cosine, không cần biết trước số speaker), trả segment kèm `speaker`.
- [x] ~~Migration thêm cột speaker vào bảng segment~~ — không cần: `transcript_json` là cột JSON trên `Video`, không phải bảng segment riêng, chỉ cần thêm key `speaker` vào từng dict (giống cách `translated_text` đã làm).
- [x] `dubbing_service.py`: thêm `run_diarize()` (gọi sau transcribe, không đổi `VideoStatus`) + `run_dub_and_mux` đọc `video.speaker_voices_json` theo `segment["speaker"]` để chọn giọng.
- [x] `tts_service.py`: `synthesize_speech` nhận `voice: dict|None` (`{"provider", "voice_id"}`), route thẳng Edge nếu `provider="edge"`, hoặc truyền `voice_id` vào ElevenLabs pool nếu `provider="elevenlabs"` — `None` giữ nguyên hành vi cũ.
- [x] API: `POST /{id}/diarize`, `GET /{id}/voices` (`voice_service.py` mới — Edge 2 giọng cố định + ElevenLabs thật từ `/v1/voices` nếu user có key), `PUT /{id}/speaker-voices`.
- [x] Frontend: bước "Phân vai người nói" trong tab Xử lý, tab mới "Giọng đọc" (`speaker-voices.tsx`) hiện câu mẫu + dropdown chọn giọng theo vai, ô chọn speaker thủ công trong `subtitle-editor.tsx` để sửa khi AI gán nhầm.
- [x] Test: 8 test mới (`test_diarization_adapter.py` cluster logic với embedding giả lập, `test_voice_service.py`, `test_tts_service.py` routing theo provider, `test_dubbing_service.py` cho `run_diarize` + forward voice) — 427 test backend, 190 test frontend, đều pass. `ruff check/format`, `eslint`, `tsc -b` sạch.

## Tiêu chí hoàn thành (Definition of Done)
- [ ] Chạy video mẫu có 2 người nói → hệ thống tự tách đúng 2 speaker (verify bằng mắt) — **CHƯA LÀM**, thiếu video mẫu (xem Ghi chú).
- [ ] Gán 2 giọng khác nhau (1 nam 1 nữ) cho 2 speaker → video lồng tiếng ra nghe đúng giọng theo từng đoạn thoại tương ứng — **CHƯA LÀM**, phụ thuộc mục trên.
- [x] Video chỉ có 1 người nói vẫn chạy được bình thường như luồng cũ — đúng theo thiết kế (`speaker` rỗng → `voice=None` → hành vi cũ y hệt) + test `test_matched_duration_*` cũ vẫn pass không đổi.
- [x] Nhạc nền tách riêng (Demucs) vẫn giữ nguyên — không đụng nhánh `keep_background`/Demucs trong `run_dub_and_mux`.

## Ghi chú phát sinh trong lúc làm

- **`torch` cài trong venv là bản CPU-only (`2.14.0+cpu`), `torch.cuda.is_available()` trả `False`** dù đã chốt "máy dev có GPU dùng được" ở mục Nguyên liệu. Code đã tự fallback CPU đúng thiết kế (`"cuda" if torch.cuda.is_available() else "cpu"`), nên không chặn — nhưng nghĩa là quyết định "chạy GPU cho nhanh" **chưa thực sự có hiệu lực**. Cần cài lại `torch`+`torchaudio` bản có CUDA (`--index-url https://download.pytorch.org/whl/cu121` hoặc bản khớp driver máy) nếu muốn tốc độ GPU thật — việc này ngoài phạm vi phiên này vì đây là thay đổi ảnh hưởng cả Whisper/Demucs đang dùng chung `torch`, cần cân nhắc riêng.
- **Chưa verify bằng video thật**: thư viện hiện đang trống (`GET /api/library` trả `[]`), nguyên liệu "video mẫu ≥2 người nói" ở mục trên vẫn chưa chuẩn bị. Đã chạy `npm run dev` + Playwright xác nhận app boot sạch, không lỗi console, nhưng KHÔNG tự mắt thấy được bước "Phân vai người nói"/tab "Giọng đọc" hoạt động trên video thật — cần bạn tải 1 video có ≥2 người nói rồi chạy thử qua UI.
- **Không đưa `diarize` vào `run_step` (batch/n8n)**: bước này cần user tự xem danh sách speaker rồi gán giọng qua UI trước khi dub, không khớp mô hình batch tự động chạy hết pipeline không cần người can thiệp — cân nhắc thêm sau nếu có nhu cầu batch nhiều video cùng cần phân vai.
- **Ngưỡng cluster `_CLUSTER_DISTANCE_THRESHOLD = 0.7`** (`diarization_adapter.py`) chọn theo kinh nghiệm phổ biến với ECAPA/voxceleb, chưa tự tay tinh chỉnh trên dữ liệu thật — nhiều khả năng cần chỉnh khi có video mẫu (tách quá nhiều vai giả hoặc gộp nhầm 2 người vào 1 vai).

### Công tắc bật/tắt trong Cài đặt (2026-09-24)
Test thật trên bản cài (video 1 người dẫn, 332 đoạn) ra **63 người nói** — ngưỡng `_CLUSTER_DISTANCE_THRESHOLD = 0.7` chưa dùng được với đoạn ngắn. Thêm khoá `speaker_diarization_enabled` (`settings_service`, mặc định **tắt**) + trang **Cài đặt > Lồng tiếng** (`features/settings/dubbing`). Tắt: `POST /api/videos/{id}/diarize` trả 409, UI ẩn bước "Phân vai người nói" + tab "Giọng đọc", `run_dub_and_mux` bỏ qua nhãn/giọng theo vai đã lưu (lồng bằng 1 giọng chung). Đã verify browser thật cả 2 trạng thái + test backend/frontend. **Việc còn lại**: chỉnh ngưỡng/gộp cụm nhỏ rồi mới nên bật mặc định.
