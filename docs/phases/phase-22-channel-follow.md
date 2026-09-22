# Phase 22: Theo dõi kênh + gợi ý video liên quan/cùng kênh

Trạng thái: **Code xong (backend + frontend), verify qua test suite** (2026-09-22) — 538 test backend (+22 test mới: channel_service 12, bilibili_client 5, trending_service 4, schema 1) + 219 test frontend (+5, `video-preview-dialog.test.tsx`) pass, `tsc -b`/`eslint` sạch. Chưa verify qua browser thật — máy dev đang có sự cố 2 tiến trình chiếm cổng 8000 không kill được (xem "Ghi chú phát sinh" ở phase-20), cần verify lại sau khi khởi động lại máy.

## Đã làm (2026-09-22)
- **Backend**: `models/channel.py` (mirror `Category`, follow-toggle từng cái), cột `Video.channel_id` (song song `author_name`). `adapters/bilibili/client.py` thêm `get_related` (công khai, không WBI) + `get_space_videos` (cần WBI, bọc lỗi risk-control thành `BilibiliRiskControlError`). `services/channel_service.py` — `upsert_seen_batch` (1 query, dedup, không N+1), `follow`/`unfollow` (đối xứng, tự tạo kênh nếu chưa từng thấy), `list_channel_videos` (suy giảm nhẹ nhàng khi risk-control). `trending_service.py` — mọi `_from_*_item` đọc thêm `mid`/`owner.mid`; `_attach_channel_info` (ghi nhận kênh + gắn `channel_is_followed`, cùng pattern chống N+1 với `_attach_library_status`); `get_related`, `get_channel_videos`. Route: `GET/PUT` follow ở `api/channels.py` (mới), `related`/`channel/{id}/videos` ở `api/trending.py`.
- **Frontend**: `video-preview-dialog.tsx` mở rộng — khối tên kênh + nút Theo dõi (`useChannelFollow` hook), 2 dải gợi ý ngang lazy-fetch ("Video tương tự"/"Video khác trong kênh", chỉ fetch khi dialog mở VÀ có `bvid`), bấm vào gợi ý đổi video ngay trong dialog (không mở dialog chồng dialog) qua `onSelectVideo`. Props mới đều optional — YouTube (`youtube-panel.tsx`) không đụng gì, hành vi cũ giữ nguyên. Chip "Kênh đã theo dõi" trong hàng tab chuyên mục ở `/discover` (`followed-channels-panel.tsx`, tái dùng `VideoGridPanel` vì `getChannelVideos` đã trả đúng hình dạng `TrendingPage`).
- **Phát hiện quan trọng qua đo thật (không có trong kế hoạch ban đầu)**: gọi `get_space_videos` với 10 kênh phổ biến thật, 1 request/kênh, không cookie — **10/10 đều bị risk-control chặn** (412 hoặc mã lỗi -352 `风控校验失败`). Tệ hơn hẳn dự đoán "risk-control nặng" trong khảo sát ban đầu — gần như CHẮC CHẮN mọi người dùng ở v1 sẽ luôn thấy thông báo suy giảm ở dải "Video khác trong kênh", không phải thỉnh thoảng. Quyết định "không thêm `bilibili_cookie` ở v1" (chốt trước khi có số đo này) vẫn giữ nguyên — không tự ý đảo — nhưng đã ghi rõ số đo thật để phiên sau cân nhắc.
- **Hệ quả của phát hiện trên**: **field mapping của `_from_space_video_item` (converter cho `x/space/wbi/arc/search`) chưa verify được bằng response thật** — 100% request thử đều bị chặn trước khi nhận được payload để đối chiếu. Converter dựa theo tài liệu cộng đồng (SocialSisterYi/bilibili-API-collect), đã ghi rõ trong docstring, cần verify lại khi có cookie hoặc may mắn né được risk-control.
- **Quyết định phát sinh (tự quyết trong lúc code)**: `channel_service.unfollow` đổi chữ ký nhận thêm `name` (đối xứng với `follow`) — tạo kênh mới nếu bỏ theo dõi 1 kênh backend chưa từng ghi nhận, tránh bug tôi tự phát hiện lúc viết endpoint (composed `follow()` rồi `unfollow()` rồi gán tay `is_followed=False` không commit — inconsistent state, đã sửa trước khi viết test).

## Mục tiêu

## Mục tiêu
Video hay đi theo seri/kênh đăng tải — hiện tool chỉ biết `author_name` (chuỗi text), không có gì để "xem thêm video của người này" hay "theo dõi kênh". Phase này thêm:
1. Trong popup xem trước video (`VideoPreviewDialog`): 1 dải "Video tương tự" (gợi ý liên quan) + 1 dải "Video khác trong kênh này", cùng nút Theo dõi kênh ngay tại đó.
2. Cơ chế theo dõi kênh bền (lưu DB), tận dụng lại chính pattern "theo dõi chuyên mục" đã có (`Category.is_followed`, xem `category_service.py`).

## Khảo sát: hiện trạng thật (đã đọc code, verify field qua API thật đã ghi sẵn trong repo + search tài liệu API cộng đồng)

### 1. Đã có `author_name`, chưa có id kênh — vá được không cần đổi kiến trúc
`Video.author_name` (`models/video.py:53`) và `TrendingVideoRead.author_name` (`schemas/trending.py:46`) chỉ lưu tên hiển thị. Nhưng dữ liệu thô Bilibili đã trả sẵn id kênh (`mid`) ở CẢ 3 nguồn đang dùng — chỉ là code hiện tại không lấy field đó ra:
- `popular` item: `owner.mid` (cạnh `owner.name` đang lấy ở `trending_service.py:122`).
- `search` item: field `mid` phẳng ở top-level item (cạnh `author`, `trending_service.py:99`).
- `ranking/region` item: cũng có `mid` phẳng (`trending_service.py:77`).

⇒ Không cần thêm lệnh gọi API nào để có `mid` — chỉ cần đọc thêm 1 field có sẵn trong response đang nhận.

### 2. API "video tương tự" đã có sẵn, rẻ, không cần ký WBI
`GET https://api.bilibili.com/x/web-interface/archive/related?bvid=...` — endpoint công khai, không cần WBI sign, trả tối đa 40 video liên quan, cùng hình dạng dữ liệu với `popular` (có `owner.mid`, `stat`, `pic`, `duration`...). Rủi ro risk-control thấp (đây là API dùng cho sidebar "video liên quan" trên chính trang xem Bilibili, traffic công khai rất lớn). Map thẳng sang `TrendingVideoRead` bằng lại `_from_popular_item`-style converter đã có.

### 3. API "video của kênh" tồn tại nhưng risk-control nặng — đây là rủi ro thật của phase này
`GET https://api.bilibili.com/x/space/wbi/arc/search?mid=...&pn=...&order=pubdate` — cần ký WBI (đã có `adapters/bilibili/wbi.py`, tái dùng được), nhưng tra cứu tài liệu cộng đồng (SocialSisterYi/bilibili-API-collect issue #1018, 2026) cho thấy endpoint này đang bị Bilibili siết risk-control **nặng hơn** cả `x/web-interface/view` (mà chính codebase này đã từng dính 412 — xem ghi chú ở `bilibili/client.py:86`): trả 412/-352, có báo cáo còn bị chặn bởi mã hoá `w_webid` với request không đăng nhập. Đây **không phải chuyện "code sai"**, mà là giới hạn phía Bilibili — không có endpoint thay thế nào "ít bị chặn hơn" như cách `get_video_cid` đã né được cho trường hợp `view`.

⇒ Mục "video khác trong kênh" phải thiết kế để **suy giảm nhẹ nhàng (graceful degradation)** khi bị chặn, không được để cả popup vỡ vì 1 API phụ lỗi. Không hứa trước với người dùng là tính năng này "luôn có kết quả".

### 4. Chưa có cookie Bilibili trong config — có thể là đòn bẩy giảm risk-control
`core/config.py` hiện chỉ có `douyin_cookie` (dòng 109), không có cookie Bilibili nào. Cookie đăng nhập (SESSDATA) thường giảm hẳn tần suất 412/-352 cho các endpoint `space/*`. Đây là điểm để cân nhắc thêm `bilibili_cookie: str = ""` optional (giống pattern Douyin) — không bắt buộc, nhưng cải thiện độ ổn định nếu người dùng tự nguyện điền.

### 5. Pattern "theo dõi" đã có sẵn 1 lần — tái dùng được gần như nguyên khối
`Category` (`models/category.py`) + `category_service.py` đã giải quyết đúng bài toán tương tự cho chuyên mục: model tối giản (`is_followed: bool`, `first_seen_at`/`last_seen_at`), tự phát hiện qua dữ liệu quét được (không hardcode danh sách), API `PUT .../followed` + `GET .../followed`. Khác biệt duy nhất: chuyên mục theo dõi là **tập nhỏ, thay thế toàn bộ mỗi lần set** (`set_followed` xoá hết rồi gán lại theo `rids` gửi lên); kênh theo dõi là **tập có thể lớn, toggle từng cái một** (theo/bỏ theo 1 kênh tại 1 thời điểm, không gửi lại cả danh sách) — nên service kênh cần `follow_channel`/`unfollow_channel` riêng thay vì `set_followed` kiểu thay toàn bộ.

### 6. Popup xem trước hiện là component "câm", chỉ có 4 field
`VideoPreviewDialog` (`components/video-preview-dialog.tsx`) nhận đúng `title/embedUrl/externalUrl/externalLabel/onClose` — dùng chung cho cả Bilibili lẫn YouTube (`trending/index.tsx`, `trending/youtube-panel.tsx`). Không có chỗ cho tác giả/kênh, không có slot nội dung phụ. Phải mở rộng props (thêm phần "gợi ý" dạng optional, chỉ bật khi có `bvid` — YouTube chưa cần tính năng này ở phase này).

### 7. Phụ thuộc Phase 20 — cần chốt thứ tự
Phase 20 (Khám phá) đang gộp `/crawl` + `/trending` thành 1 màn, và đúng người dùng đang sửa code ở phiên khác **có thể chính là Phase 20**. `VideoGridPanel`/`VideoPreviewDialog` mà phase này chạm vào sẽ bị Phase 20 di chuyển/đổi tên (`features/discover/`). Nếu Phase 20 chưa merge xong, code Phase 22 ở đúng những file đó sẽ bị conflict. **Đề xuất: Phase 22 làm SAU khi Phase 20 xong** (hoặc ít nhất sau khi `VideoGridPanel` đã dọn xong vị trí mới) — phần backend (model, adapter, service) có thể làm độc lập trước vì không đụng file frontend đang đổi.

## Thiết kế đề xuất

### Data model
```python
# models/channel.py — mirror Category, khác ở chỗ follow-toggle từng cái
class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("platform", "channel_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[Platform] = mapped_column(Enum(Platform))
    channel_id: Mapped[str] = mapped_column()   # Bilibili: str(mid)
    name: Mapped[str] = mapped_column()
    avatar_url: Mapped[str | None] = mapped_column(default=None)
    is_followed: Mapped[bool] = mapped_column(default=False)
    first_seen_at: Mapped[datetime] = mapped_column(...)
    last_seen_at: Mapped[datetime] = mapped_column(...)  # cập nhật mỗi lần thấy lại
```
- `Video.channel_id: str | None` — thêm cột (dùng chung migration "add column if missing" đã có ở `core/db.py`), điền song song với `author_name` ở mọi nơi đang set `author_name` (`crawl_service.py`, `trending_service.py`). Không đổi `author_name` hiện có, chỉ bổ sung.
- `TrendingVideoRead` thêm `channel_id: str | None`, `channel_is_followed: bool = False` — cùng cách annotate batch-query đã dùng cho `already_in_library` ở Phase 20 (1 query `IN (...)` sau khi dựng list, không N+1).

### Backend
- `bilibili/client.py` thêm 2 method:
  - `get_related(bvid) -> list[dict]` — gọi `x/web-interface/archive/related`, không cần WBI.
  - `get_space_videos(mid, page, page_size=25) -> list[dict]` — gọi `x/space/wbi/arc/search` qua `wbi.sign_params`; **bắt riêng lỗi risk-control** (code -352/-412 hoặc HTTP 412) thành 1 exception loại riêng (`BilibiliRiskControlError`, kế thừa `BilibiliApiError`) để caller phân biệt được "kênh này thật sự không có video" với "bị chặn, thử lại sau".
- `channel_service.py` mới (mirror `category_service.py`):
  - `upsert_seen(db, platform, channel_id, name, avatar_url=None)` — gọi mỗi khi build `TrendingVideoRead`/`Video` mà có mid, giống cách `discover_categories` học chuyên mục mới nhưng ở mức từng video một (không cần job quét riêng).
  - `follow(db, platform, channel_id) / unfollow(...)`.
  - `get_followed(db, platform) -> list[Channel]`.
  - `list_channel_videos(db, platform, channel_id, page)` — gọi adapter, khi dính `BilibiliRiskControlError` trả `TrendingPageRead(videos=[], page=page, has_more=False, source="popular")` kèm cờ lỗi riêng (`degraded: bool = True` thêm vào schema) thay vì raise 500 — frontend hiện "Bilibili đang giới hạn, thử lại sau" thay vì vỡ UI.
- `trending_service.py`:
  - `get_related(db, bvid) -> TrendingPageRead` — convert kết quả `get_related` bằng converter kiểu `_from_popular_item`, annotate `already_in_library`/`channel_is_followed` như các hàm khác.
  - Mọi `_from_*_item` hiện có: đọc thêm `mid`/`owner.mid`, set `channel_id`.
- `api/trending.py` (hoặc `api/channels.py` nếu tách gọn hơn — xem câu hỏi cần chốt):
  - `GET /api/trending/bilibili/related?bvid=` → `TrendingPageRead`.
  - `GET /api/trending/bilibili/channel/{channel_id}/videos?page=` → `TrendingPageRead` (có thể `degraded=true`).
  - `PUT /api/channels/bilibili/{channel_id}/followed` body `{followed: bool}` → trạng thái mới.
  - `GET /api/channels/followed?platform=bilibili` → `list[ChannelRead]`.
- Cân nhắc (không bắt buộc v1): `core/config.py` thêm `bilibili_cookie: str = ""`, gắn vào header `Cookie` của `BilibiliClient` nếu có — giảm tần suất risk-control cho `get_space_videos`. Để trống thì hành vi y như hiện tại.

### Frontend
- `VideoPreviewDialog` mở rộng props: thêm `channel?: { id: string; name: string; isFollowed: boolean } | null` và `bvid?: string | null`. Khi có `bvid`:
  - Header thêm dòng tên kênh + nút "Theo dõi"/"Đang theo dõi" (toggle gọi `PUT /followed`).
  - Dưới nút mở tab ngoài: 2 dải ngang cuộn được, mỗi dải là danh sách thẻ nhỏ (thumbnail + tên, tái dùng đúng `VideoCard`/thumbnail đang dùng ở lưới Trending, chỉ thu nhỏ):
    - "Video tương tự" — từ `GET .../related?bvid=`.
    - "Video khác trong kênh" — từ `GET .../channel/{id}/videos`; nếu response `degraded=true` → hiện dòng nhỏ "Bilibili đang giới hạn truy cập kênh, thử lại sau" thay vì danh sách trống im lặng.
  - Bấm vào 1 thẻ gợi ý: **không mở dialog mới** — đổi `title`/`embedUrl`/`bvid`/`channel` ngay trong dialog đang mở (state do component cha giữ, cha chỉ cần 1 setter `selectVideo`), giữ người dùng ở lại luồng khám phá liên tục thay vì bấm-đóng-mở lặp lại.
- Lazy-fetch 2 dải trên chỉ khi dialog đang mở (tránh gọi API khi popup chưa mở), fetch song song bằng React Query, mỗi cái show skeleton riêng — không chặn video nhúng hiển thị ngay.
- Vị trí "Kênh đã theo dõi" (xem trước, chưa chốt route cụ thể): 1 khối nhỏ hiển thị danh sách kênh đã theo dõi + link "xem video mới" — đặt ở đâu phụ thuộc layout thật của Phase 20 lúc đó, chưa thiết kế chi tiết ở đây (xem câu hỏi cần chốt #3).

## Nguyên liệu cần chuẩn bị trước khi bắt đầu
- [x] Xác nhận `mid`/`owner.mid` có sẵn trong response `popular`/`search`/`ranking` — không cần API mới để lấy id kênh.
- [x] Xác nhận endpoint `archive/related` công khai, không cần WBI, rủi ro risk-control thấp.
- [x] Xác nhận endpoint `space/wbi/arc/search` risk-control nặng (tra cứu tài liệu cộng đồng, chưa test request thật trong phiên này) — **cần test thật bằng vài chục request liên tiếp trước khi code**, để biết tần suất 412/-352 thực tế và có cần `bilibili_cookie` ngay từ đầu hay để sau.
- [x] **Chốt**: Phase 22 bắt đầu **sau khi Phase 20 xong hẳn** — không chạy song song. Lý do: working tree lúc khảo sát đang sửa dở đúng `trending.py`/`trending_service.py`/`crawl.py`/`pipeline.py`/`download_service.py` (backend Phase 20), và Phase 22 sẽ sửa lại các file đó lần nữa — làm song song chắc chắn conflict, không đáng để tiết kiệm thời gian chờ.
- [x] **Chốt**: KHÔNG thêm `bilibili_cookie` ở v1. Để `None` — client chạy y như hiện tại (không cookie), chấp nhận `get_space_videos` có thể bị risk-control thường xuyên hơn, xử lý bằng `degraded=True` đã thiết kế. Chỉ thêm cookie sau nếu đo thật thấy tần suất chặn quá cao để dùng được — tránh làm phức tạp v1 vì 1 rủi ro chưa đo được mức độ thật.
- [x] **Chốt route**: tách `api/channels.py` riêng. Lý do: `Channel.platform` được thiết kế đa nền tảng ngay từ đầu (mục 4 câu hỏi dưới — Douyin dùng lại sau), trong khi `api/trending.py` hiện chỉ có route Bilibili (`prefix="/api/trending/bilibili"`) — nhét route theo-kênh vào đó sẽ lẫn 2 mối quan tâm khác nhau. Riêng 2 route đọc dữ liệu Bilibili thuần tuý (`related`, `channel/{id}/videos`) vẫn đặt ở `api/trending.py` (cùng nhóm với các route Bilibili khác đang có); 2 route follow/unfollow + list-followed (platform-generic) đặt ở `api/channels.py` mới.

## Việc cần làm

### Backend
- [x] `models/channel.py` — model `Channel` (mirror `Category`, follow-toggle từng cái thay vì set toàn bộ).
- [x] `models/video.py` — thêm cột `channel_id: str | None`.
- [x] `schemas/trending.py` — `TrendingVideoRead` thêm `channel_id`, `channel_is_followed`; `TrendingPageRead` thêm `degraded: bool = False`; thêm `ChannelRead`, `SetChannelFollowedRequest`.
- [x] `adapters/bilibili/client.py` — `get_related`, `get_space_videos` + `BilibiliRiskControlError` (bắt cả HTTP 412 lẫn mã lỗi payload -352/-412).
- [x] `services/channel_service.py` mới — `upsert_seen_batch`, `follow`, `unfollow` (đối xứng, nhận `name` để tự tạo kênh mới), `get_followed`, `list_channel_videos` (bọc risk-control thành `degraded`).
- [x] `services/trending_service.py` — mọi `_from_*_item` đọc thêm `mid`; thêm `get_related`, `get_channel_videos`, `_from_space_video_item`; `_attach_channel_info` batch upsert + gắn `channel_is_followed` (không N+1).
- [x] `services/crawl_service.py` — set `channel_id` song song `author_name` ở cả 3 chỗ đang tạo `Video` (kể cả `SelectedVideo` từ Phase 20 — thêm field `channel_id` vào schema đó).
- [x] `api/channels.py` (mới) — follow/unfollow/get-followed. `api/trending.py` — `related`, `channel/{id}/videos`.
- [x] `core/db.py` — thêm cột `channel_id` vào danh sách "add column if missing".
- [x] Test: `upsert_seen_batch` idempotent + dedup trong cùng batch + không tự bật `is_followed` khi chỉ "thấy lại" (12 test `test_channel_service.py`); `list_channel_videos` trả `degraded=True` đúng khi risk-control, không nuốt lỗi khác (mock adapter); `get_related`/`get_channel_videos` map field đúng (`test_trending_service.py`); `get_space_videos` phân biệt đúng HTTP 412 / mã -352 / lỗi khác (5 test `test_bilibili_client.py`).

### Frontend
- [x] `video-preview-dialog.tsx` — mở rộng props (tất cả optional, YouTube không đụng gì), khối tên kênh + nút theo dõi, 2 dải gợi ý lazy-fetch (`enabled` chỉ khi dialog mở), đổi video đang xem ngay trong dialog qua `onSelectVideo`.
- [x] `lib/api.ts` — `getRelatedVideos`, `getChannelVideos`, `getFollowedChannels`, `setChannelFollowed`.
- [x] Hook `useChannelFollow` (`hooks/use-channel-follow.ts`) — invalidate cache `['channels','followed']` sau khi toggle.
- [x] Chip "Kênh đã theo dõi" trong hàng tab chuyên mục ở `/discover` — v1 đơn giản (chọn 1 kênh, xem video kênh đó, tái dùng `VideoGridPanel`), đúng phương án đơn giản plan đã chấp nhận.
- [x] Test: `video-preview-dialog.test.tsx` +5 case (không có bvid → không gọi API kênh; có bvid → hiện tên kênh + gọi đúng 2 API; bấm Theo dõi gọi đúng tham số; `degraded=true` hiện thông báo suy giảm không phải danh sách rỗng; bấm gợi ý gọi `onSelectVideo` và KHÔNG mở dialog thứ 2).

## Tiêu chí hoàn thành (Definition of Done)
- [~] Mở popup xem trước 1 video Bilibili thật → thấy tên kênh, nút Theo dõi bấm được, dải "Video tương tự" có kết quả thật — **chưa verify qua browser** (sự cố cổng 8000, xem "Ghi chú phát sinh" phase-20); logic đã verify qua test (mock đúng field response thật của `archive/related`).
- [x] Dải "Video khác trong kênh" bị risk-control thì hiện đúng thông báo suy giảm, không crash popup — verify qua test (`degraded=true` render đúng, không phải danh sách rỗng im lặng) **và** verify gián tiếp qua đo thật (10/10 request risk-control thật không làm crash backend, `BilibiliRiskControlError` được bắt đúng).
- [x] Bấm vào 1 thẻ gợi ý → dialog đổi sang video đó ngay tại chỗ, không mở dialog chồng dialog — verify qua test (`onSelectVideo` gọi đúng video, `document.querySelectorAll('[role=dialog]').length === 1`).
- [x] Theo dõi 1 kênh → tải lại app → trạng thái theo dõi vẫn còn (persist DB thật) — verify qua test service layer với DB SQLite thật (không mock), không phải state FE.
- [x] `tsc -b` + `eslint` sạch; test backend (538) + frontend (219) pass; không phá test hiện có của `video-preview-dialog.test.tsx` (3 test cũ vẫn xanh, +5 test mới).

## Quyết định đã chốt (tự quyết thay người dùng — vắng mặt, uỷ quyền 2026-09-22)
Ghi lại lý do để phiên code sau không cần hỏi lại hay đoán.

1. **Thứ tự với Phase 20**: làm **sau khi Phase 20 merge xong**, không chạy song song. Lý do đã ghi ở mục Khảo sát #7 — cùng chạm `VideoPreviewDialog`/`VideoGridPanel`/`trending_service.py`, làm song song chắc chắn conflict.
2. **"Kênh đã theo dõi" hiển thị ở đâu**: **1 chip lọc "Kênh đã theo dõi" ngay trong hàng chip chuyên mục ở lưới Khám phá** (`/discover`), KHÔNG thêm mục sidebar riêng, KHÔNG thêm tab Insights riêng. Lý do: Phase 20 vừa chủ động gộp 3 mục điều hướng xuống 2 để giảm rối; thêm 1 đích điều hướng mới cho Phase 22 đi ngược hướng đó. Chip lọc tái dùng đúng UI hàng chip đã có (`[Tất cả] [Đời sống] [Ẩm thực]...` ở phase-20), chỉ thêm 1 chip nữa, khi chọn thì lưới đổi sang hợp danh sách video mới nhất từ các kênh đã theo dõi (query nhiều `list_channel_videos` song song, hoặc đơn giản hơn ở v1: chỉ hiện danh sách kênh + link bấm vào từng kênh, ghép nhiều kênh thành 1 feed để sau nếu cần).
3. **Thông báo "kênh có video mới" (polling nền)**: **ngoài phạm vi v1**. Lý do đã ghi sẵn trong khảo sát: `space/*` vốn rủi ro risk-control cao, polling định kỳ nhân số lần gọi lên nhiều lần trong khi chưa đo được tần suất chặn thật — làm sau khi có số liệu thật từ v1 thủ công.
4. **Douyin có cần theo dõi kênh ở phase này?**: **không** — chỉ làm Bilibili. `Channel.platform` (kiểu `Platform` enum có sẵn) để sẵn chỗ cho Douyin dùng lại khi Phase 3 hết blocked, không code nhánh Douyin bây giờ.
5. **`bilibili_cookie` (SESSDATA)** và **route đặt ở đâu**: xem 2 dòng `[x]` tương ứng ở mục "Nguyên liệu cần chuẩn bị trước khi bắt đầu" phía trên — đã chốt: không thêm cookie ở v1; follow/unfollow/list-followed vào `api/channels.py` mới, `related`/`channel videos` giữ ở `api/trending.py`.
