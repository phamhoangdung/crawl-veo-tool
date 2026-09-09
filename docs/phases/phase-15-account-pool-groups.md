# Phase 15: Account Pool — pool-group cho provider quota-theo-project (Google Veo)

Trạng thái: Chưa bắt đầu — phụ thuộc Phase 14 (cần có nhu cầu gọi Google Veo thật trước khi giải quyết vấn đề pool của nó; nếu Phase 14 chỉ dùng fal.ai/Kling xong xuôi mà chưa cần Veo trực tiếp, phase này có thể hoãn vô thời hạn). Bối cảnh/lý do: [docs/ai-video-generation/research.md](../ai-video-generation/research.md) mục "Phần 4: Account Pool áp dụng cho video-gen — có vấn đề".

## Vấn đề cần giải quyết
Cơ chế Account Pool hiện tại ([Phase 8](phase-8-ai-account-pool.md)) giả định **mỗi row `ApiKey` = 1 quota độc lập** — đúng với OpenAI/ElevenLabs/DeepL/fal.ai/Kling (1 key = 1 tài khoản = 1 hạn mức riêng). Google Gemini API/Vertex AI (dùng cho Veo) **không theo mô hình đó**: rate limit/quota tính theo **GCP project**, mọi API key sinh ra trong cùng 1 project chia sẻ chung 1 hạn mức.

Hậu quả nếu dùng nguyên cơ chế Phase 8 cho Google: người dùng thêm 2 key Google cùng 1 project vào pool, tưởng đã tăng gấp đôi khả năng chịu tải — nhưng `pick_key_for_task` xoay sang "key 2" khi "key 1" bị 429 thì key 2 **cũng 429 ngay lập tức** vì cùng cạn 1 quota chung. Rotation chạy đúng logic nhưng vô nghĩa về mặt quota thật, và tệ hơn: log/UI sẽ hiển thị "đã chuyển key" khiến người dùng lầm tưởng hệ thống đang failover đúng trong khi job vẫn treo `PAUSED_QUOTA` liên tục.

## Mục tiêu
Phân biệt rõ 2 loại provider trong Account Pool: **loại A** ("key độc lập" — rotation theo key như hiện tại, giữ nguyên không đổi) và **loại B** ("key chung nhóm quota" — rotation phải theo **nhóm** (project), không theo key lẻ). Cho phép pool đúng nghĩa với Google bằng cách thêm nhiều **project** (mỗi project 1+ key, có thể nhiều region), không phải nhiều key rời trong cùng 1 project.

## Phạm vi
**Trong phạm vi:** thêm field `pool_group` (nullable) vào `ApiKey` — key nào cùng `pool_group` bị coi là share chung 1 quota, rotation phải nhảy sang key ở `pool_group` khác thay vì key bất kỳ cùng provider; validate ở tầng UI/API không cho thêm key Google mà không khai báo `pool_group` (bắt buộc với provider được đánh dấu "quota theo nhóm"); cảnh báo rõ trên UI khi 2 key cùng `pool_group` (giải thích: "2 key này dùng chung 1 hạn mức, KHÔNG tăng khả năng chịu tải — muốn tăng thật cần tạo project GCP mới"); cập nhật `pick_key_for_task`/`mark_key_result` để cooldown áp dụng cho **cả nhóm** cùng lúc khi 1 key trong nhóm báo 429 (vì các key cùng nhóm chắc chắn cũng đang cạn).

**Ngoài phạm vi:** tự động tạo GCP project mới qua API (người dùng tự tạo project + service account trên Google Cloud Console, tool chỉ quản lý key/nhóm sau khi đã có); tích hợp Vertex AI đầy đủ (service account JSON, region config) — phase này chỉ xử lý phần model/logic pool, việc tích hợp gọi Veo thật nằm ở Phase 14 hoặc phase tích hợp Veo riêng nếu tách ra sau; billing API thật để biết quota còn lại chính xác (vẫn tự đếm lỗi 429 như Phase 8).

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [ ] **Xác nhận Phase 14 đã cần Google Veo trực tiếp chưa** — nếu chưa (vẫn dùng fal.ai/Kling ổn), cân nhắc hoãn phase này, tránh làm trước khi có nhu cầu thật.
- [ ] **Ít nhất 2 GCP project riêng biệt, mỗi project có billing account riêng** — cần thiết để tự tay verify pool THẬT tăng khả năng chịu tải (không chỉ test bằng project giả định trong code).
- [ ] Quyết định: `pool_group` là free-text (người dùng tự đặt tên project để nhóm, đơn giản) hay bắt buộc nhập đúng GCP Project ID (chặt chẽ hơn nhưng cần validate)?

## Việc cần làm

### Backend
- [ ] `app/models/api_key.py`: thêm `pool_group: Mapped[str | None]` — nullable, chỉ có ý nghĩa với provider "quota theo nhóm" (Google). Migration `ALTER TABLE ADD COLUMN` qua `ensure_schema_columns()` (không đụng constraint, không cần dựng lại bảng như migration Phase 8).
- [ ] `app/services/api_key_service.py`: thêm hằng số/danh sách `_GROUPED_QUOTA_PROVIDERS` (bắt đầu với `{"google"}`) — `add_key` validate bắt buộc `pool_group` khi provider nằm trong danh sách này.
- [ ] `pick_key_for_task`: với provider thuộc `_GROUPED_QUOTA_PROVIDERS`, sau khi chọn ứng viên theo LRU như cũ, nếu ứng viên đó `cooldown` thì bỏ qua **toàn bộ key cùng `pool_group`** (không chỉ 1 key) khi tìm ứng viên tiếp theo — tránh chọn "key khác" nhưng thực ra cùng nhóm đã cạn.
- [ ] `mark_key_result` (khi `success=False`): với provider thuộc `_GROUPED_QUOTA_PROVIDERS`, đặt `cooldown` cho **mọi key cùng `pool_group`** với key vừa lỗi, không chỉ riêng key đó — vì chắc chắn cả nhóm đang cạn chung.
- [ ] `app/schemas/api_key.py` + `app/api/api_keys.py`: thêm `pool_group` vào request/response, trả lỗi rõ ràng (400) khi thiếu `pool_group` cho provider bắt buộc.
- [ ] Test: `pick_key_for_task` bỏ qua đúng cả nhóm khi 1 key trong nhóm cooldown (khác hành vi hiện tại — chỉ skip đúng 1 key); `mark_key_result` cooldown cả nhóm; `add_key` từ chối khi thiếu `pool_group` cho provider Google; provider ngoài danh sách (OpenAI/ElevenLabs/fal.ai...) hành vi **giữ nguyên y hệt** Phase 8 (test regression, không được đổi).

### Frontend
- [ ] `frontend/src/features/api-keys/index.tsx`: khi thêm key provider Google, bắt buộc nhập `pool_group` (gợi ý placeholder "GCP Project ID hoặc tên bạn tự đặt để nhóm"); hiển thị badge nhóm cạnh mỗi key; cảnh báo inline khi phát hiện 2 key cùng nhóm ("2 key này dùng chung 1 hạn mức").
- [ ] `frontend/src/lib/api.ts`: thêm `pool_group` vào type `ApiKeyRead`/`ApiKeyCreate`.

## Tiêu chí hoàn thành (Definition of Done)
- [ ] Thêm 2 key Google cùng `pool_group` → mô phỏng lỗi quota ở key 1 → key 2 (cùng nhóm) cũng chuyển `cooldown` ngay, KHÔNG được chọn tiếp — verify qua test.
- [ ] Thêm 2 key Google khác `pool_group` (đại diện 2 GCP project khác nhau) → mô phỏng lỗi quota ở nhóm 1 → hệ thống chuyển đúng sang key ở nhóm 2, vẫn hoạt động — verify qua test, và nếu có 2 project GCP thật thì tự tay verify bằng key thật.
- [ ] Toàn bộ test hiện có của Phase 8 (OpenAI/ElevenLabs rotation) vẫn pass nguyên vẹn — xác nhận thay đổi không phá hành vi provider loại A.
- [ ] UI chặn rõ ràng khi thêm key Google thiếu `pool_group`, kèm giải thích ngắn gọn lý do bắt buộc.

## Ghi chú phát sinh trong lúc làm
(Điền khi bắt đầu code.)
