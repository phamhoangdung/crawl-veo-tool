# Phase 2: AI Pipeline MVP (1 provider)

Trạng thái: Chưa bắt đầu (phụ thuộc Phase 1)

## Mục tiêu
Từ 1 video đã tải (Phase 1), chạy hết pipeline: transcribe → dịch → TTS → mux, ra video lồng tiếng cơ bản. Chưa tách nhạc nền, chưa phụ đề — mục tiêu là có 1 đường ống chạy được đầu-cuối với 1 provider.

## Phạm vi
**Trong phạm vi:** `faster-whisper` transcribe, 1 provider dịch, 1 provider TTS, mux bằng ffmpeg (thay toàn bộ audio track, chưa giữ nhạc nền gốc), chế độ nhập/sửa kịch bản dịch thủ công thay auto-translate.

**Ngoài phạm vi:** đa provider, tách nhạc nền, phụ đề, Douyin.

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [ ] Chọn provider dịch cho MVP (khuyến nghị OpenAI GPT nếu đã có key sẵn) — cần API key thật.
- [ ] Chọn provider TTS cho MVP: khuyến nghị bắt đầu **Edge-TTS** (miễn phí, không cần key) để chạy thử pipeline nhanh, chuyển sang ElevenLabs/Azure sau khi pipeline đã chạy ổn (cần API key nếu chọn hướng này).
- [ ] Cài `faster-whisper`, xác nhận chạy được trên máy (CPU trước, GPU nếu có driver).
- [ ] Có sẵn 1 video đã tải từ Phase 1 để test end-to-end.

## Việc cần làm
- [ ] Adapter `translate()` cho provider dịch đã chọn.
- [ ] Adapter `tts()` cho provider TTS đã chọn.
- [ ] Service transcribe dùng `faster-whisper`, xuất transcript kèm timestamp theo câu.
- [ ] UI cho phép xem/sửa transcript và bản dịch thủ công trước khi generate giọng.
- [ ] Service mux: ghép audio TTS mới vào video gốc bằng ffmpeg (thay toàn bộ track âm thanh).
- [ ] Job chạy qua `ProcessPoolExecutor`, cập nhật đủ các trạng thái state machine qua từng bước.
- [ ] Trang UI theo dõi tiến trình pipeline theo từng video.

## Tiêu chí hoàn thành (Definition of Done)
- Chạy 1 video mẫu hết pipeline, ra video có giọng đọc mới.
- Nghe hiểu được nội dung đã dịch, đối chiếu bằng tai với bản gốc thấy hợp lý.
- Sửa transcript/bản dịch thủ công trước khi render hoạt động đúng (không bị ghi đè bởi auto-translate).

## Ghi chú phát sinh trong lúc làm
*(để trống, cập nhật khi làm)*
