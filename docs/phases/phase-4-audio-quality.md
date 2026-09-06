# Phase 4: Audio Quality (tách nhạc nền) + Video dài

Trạng thái: **Phần lõi xong & verify thật** (tách nhạc nền + time-stretch). Chunking cho video dài **chưa làm** — xem Ghi chú lý do.

## Mục tiêu
Giữ nhạc nền/hiệu ứng gốc khi lồng tiếng thay vì thay toàn bộ track âm thanh; xử lý được video dài mà không tràn RAM/timeout.

## Phạm vi
**Trong phạm vi:** Demucs tách vocal/nhạc nền, mix giọng mới với nhạc nền đã tách, time-stretch khớp thời lượng câu, chunk video dài theo khoảng lặng trước khi transcribe/tách nhạc.

**Ngoài phạm vi:** phụ đề, thư viện quản lý video.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [x] Cài `demucs`, xác nhận chạy được trên CPU (model `htdemucs`, tự tải lần đầu ~80MB).
- [ ] 1 video mẫu dài (>10 phút) để test chunk theo khoảng lặng — **không có**, xem Ghi chú.
- [x] Time-stretch: chọn **ffmpeg filter `atempo`** (đơn giản, không cần cài thêm binary như `pyrubberband`) — verify hoạt động đúng qua test mocked + chạy thật.

## Việc cần làm
- [x] `app/adapters/demucs.py`: `separate_vocals()` gọi `python -m demucs --two-stems=vocals` qua subprocess, trả về đường dẫn `vocals.wav`/`no_vocals.wav`.
- [x] `app/adapters/ffmpeg.py`: thêm `extract_audio()`, `time_stretch()` (atempo, clamp [0.5, 2.0]), `mix_audio_tracks()` (amix).
- [x] `dubbing_service.run_dub_and_mux()` viết lại: mỗi câu TTS xong được time-stretch khớp `end - start` của đoạn gốc (bỏ qua nếu lệch <5%, tránh re-encode không cần thiết); nếu `keep_background=True` (mặc định) thì tách audio gốc bằng Demucs, trộn giọng mới với `no_vocals.wav` thay vì ghi đè track gốc hoàn toàn.
- [x] API `POST /api/videos/{id}/dub?keep_background=true|false` — tham số bật/tắt giữ nhạc nền (đáp ứng yêu cầu UI, hiện mới có ở API level, chưa có toggle trên giao diện Crawl).
- [ ] Silence-based chunking cho video dài trước khi Demucs/transcribe — **chưa làm**, xem Ghi chú.
- [ ] Toggle bật/tắt giữ nhạc nền trên UI (hiện chỉ đổi được qua query param API) — nhỏ, để lại cho phiên sau khi cần.

## Tiêu chí hoàn thành (Definition of Done)
- [x] Video lồng tiếng ra vẫn nghe được nhạc nền/hiệu ứng gốc — verify bằng kỹ thuật (không nghe trực tiếp được): MD5 của `voice_timeline.mp3` (chỉ giọng) khác `dubbed_audio.mp3` (đã trộn); `no_vocals.wav` có `mean_volume -23.9dB` (không phải im lặng); `dubbed_audio.mp3` có volume riêng biệt (-27.7dB) khác cả 2 track gốc — chứng tỏ đã trộn thật, không phải ghi đè hay bỏ qua bước mix.
- [ ] Xử lý được video dài (>10 phút) không lỗi tràn RAM/timeout — **chưa test được**, xem Ghi chú.
- [~] Giọng đọc khớp thời lượng đoạn gốc — cơ chế time-stretch đã cài đặt và verify bằng test (factor tính đúng, gọi `ffmpeg.time_stretch` đúng khi lệch >5%, bỏ qua khi gần đúng), đã chạy thật trên video mẫu không lỗi; chưa tự nghe kiểm tra độ tự nhiên bằng tai.

## Ghi chú phát sinh trong lúc làm
- **Không làm chunking cho video dài vì không có video mẫu dài (>10 phút) để test, và bạn không có mặt để cung cấp lúc tôi làm phần này.** Cân nhắc kỹ: có thể viết code chunking "cho có" nhưng không verify được liệu nó thực sự đúng (vd merge lại timestamp giữa các chunk có lệch không) — quyết định KHÔNG viết code chưa kiểm chứng được thay vì tạo rủi ro âm thầm (chunking sai còn tệ hơn không chunking). Việc cần làm khi có video dài thật: (1) thử chạy thẳng pipeline hiện tại xem có thực sự tràn RAM/timeout không (faster-whisper `small` xử lý audio theo từng cửa sổ 30s nội bộ nên có thể đã đủ ổn với CPU cho video dài, chỉ Demucs mới thực sự nặng vì xử lý cả waveform cùng lúc), (2) nếu có vấn đề thật, ưu tiên chunk riêng cho bước Demucs (theo khoảng lặng, dùng `pydub.silence`) trước, vì đó là bước tốn RAM nhất, chưa chắc cần chunk cho Whisper.
- Xác nhận thật: `voice_timeline.mp3` và `dubbed_audio.mp3` (video test 141s) tình cờ **bằng byte size** (564428 bytes) dù nội dung khác nhau — ban đầu tưởng bug (mix không chạy), kiểm tra bằng MD5 hash mới xác nhận đây chỉ là trùng hợp về kích thước file mp3, không phải lỗi thật. Bài học: đừng chỉ dựa vào file size để verify audio đã xử lý đúng chưa, cần kiểm tra nội dung thật (hash, volume, hoặc nghe).
- Demucs chạy trên CPU cho video 141s mất khá lâu hơn transcribe/TTS cộng lại — cần lưu ý thời gian xử lý sẽ tăng đáng kể với video dài hơn, đây cũng là lý do ưu tiên chunk Demucs trước nếu cần tối ưu sau này.
