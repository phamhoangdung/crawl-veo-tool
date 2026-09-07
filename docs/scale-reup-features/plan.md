# Mở rộng: Re-up quy mô lớn (Bilibili/Douyin → YouTube/TikTok) + AI Account Pool

Trạng thái: **Ý tưởng/research, chưa lên phase thực thi** — tài liệu tham khảo kiến trúc, không phải checklist (xem `docs/phases/` khi tính năng nào ở đây được chốt để làm).

## Bối cảnh yêu cầu

Bạn muốn mở rộng tool cho 3 loại nội dung:
- **(A) Re-up video** (ngắn/dài) từ Bilibili/Douyin — đã có phần lõi (dịch + lồng tiếng + phụ đề song ngữ).
- **(B) Video "kể chuyện"** — ghép giọng đọc (kịch bản tự viết hoặc AI hỗ trợ) vào 1 video nền ngẫu nhiên (kiểu kênh Reddit-story/Minecraft-parkour background).
- **(C) Cắt clip ngắn cho TikTok** để kéo view/traffic về video dài trên YouTube.

Và 1 hạ tầng riêng: **AI Account Pool** — nhiều tài khoản/API key AI, tự phân công qua n8n, tự chuyển account khi 1 account hết quota.

Câu hỏi gốc có nhắc "tránh chính sách trung thực của YouTube" — mình đã research kỹ phần này trước khi lên plan vì nó quyết định cả hướng thiết kế tính năng (xem mục ngay dưới), không né tránh mà đối diện thẳng.

## Điều quan trọng nhất rút ra từ research: "né chính sách" và "tuân thủ đủ transform" là 2 hướng đi khác nhau

YouTube **không có chính sách "trung thực" (authenticity policy)** dưới tên đó — cái gần nhất là 2 chính sách đã có từ trước, và cả 2 đều **siết mạnh trong 2025-2026**:

1. **Reused Content policy** (điều kiện kiếm tiền): nội dung reup/clip/compilation vẫn được bật kiếm tiền **nếu** người xem thấy rõ bạn đã biến đổi nó — bằng commentary có phân tích thật, editing kể lại câu chuyện theo góc nhìn riêng, hoặc đóng khung giáo dục/ngữ cảnh. Cắt gọn + thêm nhạc + đổi transition (đúng thứ pipeline hiện tại đang làm ở mức tối thiểu) **không còn được tính là "transformative" nữa** kể từ đợt siết chính sách gần đây.
2. **Inauthentic Content policy** (đổi tên từ "Repetitious Content" tháng 7/2025): nhắm thẳng vào nội dung sản xuất hàng loạt theo template — cấu trúc lặp lại, giọng đọc AI đồng nhất, hình ảnh na ná nhau giữa các video. Điểm quan trọng: **YouTube giờ detect ở cấp độ kênh, không chỉ từng video** — tức là dù từng video "sạch", cả kênh vẫn có thể bị đánh vì pattern lặp lại xuyên suốt. Ca thực tế tháng 1/2026: 16 kênh (tổng 35 triệu sub, 4.7 tỷ view) bị terminate; 1 kênh kể chuyện Kinh Thánh (~588K sub, ~$30K/tháng) bị mất kiếm tiền toàn kênh vì giọng đọc AI đồng nhất + hình nền template + cấu trúc lặp lại hàng trăm video.

**Hệ quả trực tiếp cho plan này:**
- Hướng **(B) video kể chuyện** — đúng pattern rủi ro cao nhất trong 2 chính sách trên nếu làm theo kiểu "1 giọng TTS cố định + rút ngẫu nhiên từ 1 kho video nền + cấu trúc intro/outro y hệt" để tối đa hoá tốc độ ra video. Plan dưới đây thiết kế tính năng **buộc phải đa dạng hoá** (voice, pacing, cấu trúc, nguồn kịch bản) ngay trong luồng sản xuất, không phải tuỳ chọn — coi đây là yêu cầu kỹ thuật bắt buộc, không phải "nice to have".
- Hướng đúng để "an toàn chính sách" cho **(A) re-up** là thêm lớp **giá trị gốc thật** (commentary/insight, ngữ cảnh hoá, giọng biên tập riêng) — không phải kỹ thuật đánh lừa hệ thống phát hiện (đổi fingerprint, giả mạo metadata, v.v.). Những kỹ thuật né tránh phát hiện đó mình sẽ không đưa vào plan: rủi ro bị terminate toàn kênh (mất luôn cả các kênh làm đúng) cao hơn nhiều lợi ích, và một số thuộc dạng vi phạm rõ ràng (spoof để đánh lừa hệ thống) nên mình không hỗ trợ thiết kế theo hướng đó.
- **Bản quyền và chính sách YouTube là 2 rủi ro tách biệt** — tuân thủ đủ để không bị YouTube phạt (transform đủ, không lặp template) không có nghĩa là hết rủi ro bản quyền với chủ sở hữu gốc (phim/nhạc/nội dung sáng tác lấy từ Bilibili/Douyin thường vốn đã là nội dung có bản quyền của bên thứ 3). Rủi ro bản quyền đã ghi ở `docs/overview/plan.md` mục 7 và `docs/phases/phase-7-productization.md` — plan này chỉ giải quyết vế chính sách nền tảng, không thay thế tư vấn pháp lý về bản quyền.

Nguồn: [vidiq — YouTube Reused Content Policy 2026](https://vidiq.com/blog/post/youtube-reused-content-policy-guide/), [AIR Media-Tech — Monetization Policy Timeline 2026](https://air.io/en/monetization/youtube-monetization-policy-changes-2026-a-complete-dated-timeline), [ytzolo — Repetitious/Inauthentic Content 2026](https://ytzolo.com/blog/youtube-repetitive-content-policy-ai-slop-2026/), [ytgrowth — AI Demonetization 2026](https://ytgrowth.io/blog/youtube-ai-policy).

## A. Re-up video — còn thiếu gì để đủ "transform"

Lõi hiện có (Phase 2-5): dịch + lồng tiếng (giữ nhạc nền) + phụ đề song ngữ. Đây là transform thật (không chỉ cắt/dán), nhưng để an toàn hơn theo policy 2026 nên thêm:

- **Lớp commentary/insight tự sinh**: cho phép chèn đoạn intro/outro do AI soạn (dựa trên transcript gốc) nêu bối cảnh/góc nhìn — khác nội dung gốc, không chỉ dịch thuần. Có thể để user tự viết tay hoặc AI gợi ý rồi user duyệt (không nên full-auto để giữ chất lượng và tính "góc nhìn riêng" thật).
- **Trình sinh title/description/tag theo văn phong riêng của kênh** (không dùng template cố định giữa các video) — tránh dấu hiệu "templated content" ở cấp kênh.
- **Source & rights ledger**: đã có gợi ý ghi nguồn ở overview plan; mở rộng thành bảng riêng lưu URL gốc, tác giả gốc, trạng thái review bản quyền — phục vụ cả compliance lẫn truy vết khi cần gỡ.
- **Disclosure nội dung có AI/lồng tiếng tổng hợp**: nên kiểm tra yêu cầu công bố "altered/synthetic content" của YouTube tại thời điểm publish thật (chính sách hay cập nhật) và có checkbox nhắc user trước khi xuất bản.

## B. Video kể chuyện — luồng sản xuất mới, không đi qua crawl

Đây là loại nội dung khác hẳn (A): không có "video nguồn" để dịch, mà là **kịch bản → giọng đọc → ghép video nền**. Cần:

- **Module kịch bản**: user tự nhập, hoặc AI hỗ trợ generate/gợi ý (khác nguồn dịch — nội dung "gốc" hơn nên an toàn hơn về cả bản quyền lẫn policy nếu kịch bản thực sự nguyên bản, không phải dịch nguyên văn 1 story có sẵn).
- **Thư viện video nền (background library)**: upload/quản lý kho video nền (gameplay, cảnh thiên nhiên...), gắn tag/category, theo dõi đã dùng với kịch bản nào để **tránh lặp cặp giọng-nền giống hệt nhau nhiều lần** — chính là điểm YouTube quét ở cấp kênh.
- **Cơ chế đa dạng hoá bắt buộc** (thiết kế như 1 ràng buộc của pipeline, không phải tuỳ chọn): rotate giữa nhiều giọng TTS, nhiều mẫu intro/outro, nhiều bố cục caption — hệ thống nên tự cảnh báo (như cost estimate hiện có) nếu phát hiện N video gần nhất dùng cùng 1 tổ hợp giọng+nền+cấu trúc.
- **Visual variety**: overlay caption động (không chỉ audio trên nền tĩnh) — tái dùng hạ tầng phụ đề/burn-in đã có ở Phase 5, style khác cho định dạng story.
- Đây là job type mới, không phải job type "crawl" — ảnh hưởng schema Job (xem mục Kiến trúc bên dưới).

## C. Cắt clip ngắn cho TikTok → kéo về YouTube

- **Auto-clip candidate**: chọn đoạn highlight dựa trên transcript (từ khoá, biến động cảm xúc câu thoại) hoặc mốc thời gian user tự đánh dấu khi preview — bắt đầu ở mức "gợi ý", không cần auto-viral-scoring phức tạp ngay từ đầu.
- **Reframe dọc 9:16**: crop thông minh theo chủ thể/khuôn mặt — đây là mảnh kỹ thuật hoàn toàn mới so với stack hiện tại (chưa có model face/subject-tracking). Đề xuất bắt đầu bằng UI crop bán tự động (user kéo khung, tool giữ khung đó xuyên suốt clip) trước khi đầu tư model auto-tracking.
- **Caption kiểu TikTok**: tái dùng subtitle service (Phase 5) nhưng thêm style động (từng từ nổi bật) — khác style phụ đề song ngữ chuẩn.
- **CTA/hook overlay**: chèn watermark/text "Xem full trên YouTube" + có thể để trống chỗ dán link trong bio.
- **Lịch đăng chéo**: tạo đồng thời bản Shorts (YouTube) + clip TikTok từ cùng 1 đoạn cắt, theo dõi UTM nếu nền tảng đích cho phép.

## AI Account Pool — thiết kế hạ tầng

Hiện trạng (`api_key_service.py`): **1 key/provider/user**, có fallback *khác provider* khi lỗi (Phase 3), nhưng **không có pool nhiều account cùng 1 provider**. Đây đúng là khoảng trống bạn nói.

### Thiết kế đề xuất
- **Đổi ràng buộc DB**: bỏ unique `(user_id, provider)`, cho phép nhiều `ApiKey` row cùng provider — mỗi row thêm field: `label` (tên gợi nhớ), `status` (`active` / `cooldown` / `exhausted` / `invalid`), `cooldown_until`, usage counter (request/token/cost — tái dùng ý tưởng đã có ở `cost_service.py`, mở rộng để track theo từng key thay vì theo job).
- **Selection strategy**: round-robin hoặc least-used trong các key `active` của 1 provider; có thể ưu tiên theo capability flags đã có sẵn trong adapter interface (ví dụ key nào hỗ trợ ngôn ngữ/tính năng cần).
- **Failover 2 tầng** (khớp với thiết kế fallback đã có ở Phase 2-3, không phá vỡ):
  1. Trong cùng provider: key lỗi 429/quota-exceeded → đánh dấu `cooldown`/`exhausted`, tự chuyển key khác cùng provider.
  2. Hết cả pool 1 provider: fallback sang provider khác đã cấu hình (cơ chế đã có).
  3. Hết tất cả: job chuyển trạng thái `paused_quota` (không fail hẳn) — tự resume khi có key mới hoặc cooldown hết hạn, thay vì để job chết.
- **Nơi đặt logic: backend (FastAPI), không phải trong n8n.** Lý do: chọn key phải là thao tác atomic (tránh 2 job cùng lúc chọn trùng 1 key đã cạn) — cần transaction ở DB, còn n8n chạy nhiều execution song song không giữ lock an toàn cho việc này. n8n giữ vai trò **orchestrator**: gọi endpoint enqueue job của backend theo batch (pattern HTTP API Integration + Batch Processing/SplitInBatches), poll trạng thái, và dùng Error Handler pattern để báo (Slack/Telegram) khi có job `paused_quota` kéo dài quá ngưỡng.
- **UI mới**: trang "AI Account Pool" trong Settings — danh sách key theo provider, trạng thái, usage/cost từng key, thêm/xoá/tạm dừng 1 key riêng lẻ (tái dùng mask key đã có).

## Quyết định kiến trúc cần chốt trước khi code

- **Job type mới cho (B)**: thêm field `job_type` (`reup` / `story` / `clip`) vào bảng Job, hay tách bảng riêng? Ảnh hưởng state machine hiện có (Phase 2) vì (B) không có bước `downloading` từ nguồn ngoài.
- **Model crop/reframe cho (C)**: build UI crop thủ công trước (nhanh, không cần model mới) hay đầu tư luôn auto-tracking? Đề xuất: thủ công trước, đo nhu cầu thật rồi mới quyết định đầu tư model.
- **Ngưỡng "đa dạng hoá" cho (B)**: cần bao nhiêu biến thể (giọng/nền/cấu trúc) tối thiểu trước khi hệ thống cảnh báo lặp? Không có con số chuẩn từ YouTube — đề xuất bắt đầu với ngưỡng tự đặt (vd. cảnh báo nếu > 30% video trong 20 video gần nhất dùng cùng tổ hợp) rồi điều chỉnh theo thực tế.
- **Cost tracking theo key**: mở rộng `cost_service.py` cần API usage thật từ provider (không phải ước tính thô như hiện tại) để biết chính xác khi nào 1 key gần cạn quota — cần kiểm tra provider nào trả về usage endpoint (OpenAI có, một số provider khác không).

## Đề xuất thứ tự làm (phase mới, nối sau Phase 7)

1. **AI Account Pool** trước tiên — hạ tầng nền, ít mơ hồ nhất, không phụ thuộc quyết định nội dung nào ở A/B/C, và cần thiết ngay khi scale bất kỳ hướng nào.
2. **Lớp compliance/value-add cho (A)** — commentary layer, title/description generator chống template, source ledger. Rủi ro thấp vì mở rộng trên nền đã chạy được thật (Phase 2-5 đã verify end-to-end).
3. **(B) Video kể chuyện** — luồng sản xuất mới hoàn toàn, cần chốt kịch bản/thư viện nền trước.
4. **(C) Clip ngắn + cross-post** — phụ thuộc (A)/(B) đã có nội dung nguồn để cắt; phần reframe dọc là rủi ro kỹ thuật cao nhất nên để sau cùng, bắt đầu bản thủ công.

Đã viết `docs/phases/phase-8-ai-account-pool.md` đến `phase-11-shorts-crosspost.md` theo đúng format checklist hiện có (kèm mục "Nguyên liệu cần chuẩn bị trước khi bắt đầu"), thứ tự đúng theo roadmap ở trên. Các câu hỏi mở dưới đây được lặp lại trong mục "Nguyên liệu" của từng phase liên quan — trả lời trực tiếp ở đó khi vào phiên code phase tương ứng.

## Việc cần chốt với bạn

- Ưu tiên AI Account Pool trước (theo đề xuất) hay ưu tiên 1 trong 3 hướng nội dung A/B/C trước?
- (B) kịch bản: bạn tự viết tay, hay cần AI hỗ trợ sinh kịch bản gốc ngay từ MVP?
- (C) reframe dọc: chấp nhận crop thủ công ở bản đầu, hay bắt buộc cần auto-tracking ngay?
- Có cần research thêm về yêu cầu "disclosure nội dung AI/synthetic" hiện hành của YouTube trước khi làm (A) không, hay để tự bạn cập nhật khi publish thật?
