# Phase 21: Tăng tốc tải video (chia phần, nhiều kết nối, tải tiếp khi lỗi)

Trạng thái: **Code xong (trừ resume — hoãn có chủ đích), verify qua test suite đầy đủ** (2026-09-22) — 516 test backend (41 test mới: settings-service 7, ranged-download 19, schema-bounds 15, cập nhật 3 test cũ) + 214 test frontend (3 test mới) pass, `tsc -b`/`eslint` sạch. Đã tự quyết (không hỏi lại, đúng hướng dẫn "pick the obvious option") **hoãn resume sang phase sau** — đúng như ghi chú "phần phức tạp nhất, multi-connection đứng một mình đã có 2,87x" đã cân nhắc sẵn trong plan.

## Đã làm (2026-09-22)
- **Hạ tầng cài đặt** (mới — tool chưa từng có cài đặt lưu được từ UI): bảng `app_settings` (khoá-giá trị theo user), `GET/PUT /api/settings`, trang "Tải xuống" trong Cài đặt (route `/settings/downloads`) — 2 ô chọn số luồng (1/2/4/8) + số video tải cùng lúc (1/2/3/5/10), đổi là lưu ngay, có giải thích rõ "trần cho cả app, không phải mỗi video" ngay tại chỗ chỉnh.
- **Tải đa luồng**: `_probe` (HEAD gộp cả size + hỗ trợ Range trong 1 request), `_download_stream` (quyết định chia phần hay fallback), `_download_range_part` (retry riêng từng phần, rollback đúng phần trăm khi lỗi giữa chừng), `_download_whole` (đường cũ, vẫn qua semaphore chung). `download_bilibili_video` nhận `connections`, đọc từ cài đặt DB **lúc bắt đầu mỗi lượt tải** (không cache).
- **1 stage tiến độ duy nhất** ("downloading") cho cả video+audio (trước đây 2 chặng nối tiếp) — dò kích thước cả 2 trước, set 1 tổng, tải song song qua `asyncio.gather`.
- **Semaphore kết nối dùng chung toàn app**, cố định ở `DOWNLOAD_CONNECTIONS_MAX=8` — số luồng người dùng chọn quyết định 1 video chia bao nhiêu phần, semaphore là hàng rào vật lý cuối cùng đảm bảo tổng không vượt 8 dù nhiều video tải cùng lúc.
- **Xử lý CDN "nói dối"**: báo `accept-ranges: bytes` nhưng GET thật trả 200 thay vì 206 → phát hiện, xoá phần dở, rơi về 1 kết nối — không ghi đè lung tung tạo file hỏng âm thầm.
- **Đổi UI khỏi kế hoạch ban đầu**: dùng `<select>` gốc thay vì Radix `Select` cho 2 ô chọn — phát hiện Radix Select là component ĐẦU TIÊN trong cả repo bị lỗi môi trường test (`Cannot read properties of null (reading 'useMemo')` trong `useScope`, do cache pre-bundle của Vite bị lệch — xoá `node_modules/.vite` sửa được lỗi crash, nhưng `<select>` gốc đơn giản hơn, nhẹ hơn, và né hẳn lớp vấn đề này cho đúng use-case "chọn 1 số trong danh sách cố định").
- **Chốt (tự quyết, đúng phạm vi phán đoán hợp lý)**: hoãn resume; `download_max_videos` đặt cùng trang "Tải xuống" với `download_connections` (đúng đề xuất ban đầu); Douyin `concurrent_fragment_downloads` chưa làm (đúng kế hoạch "đo trước rồi hãy làm", chưa đo).
- **Verify thật với video Bilibili thật 200MB (không mock)**: tải cùng 1 video bằng 1 luồng và 8 luồng, so `sha256` file cuối cùng. **1 luồng: 279s (0.72 MB/s). 8 luồng: 32.3s (6.19 MB/s) — nhanh gấp 8.64x**, vượt cả số đo benchmark cô lập ban đầu (2.87x, đo trên đoạn 16MB ngắn — video thật dài hơn nên amortize được chi phí bắt tay TLS tốt hơn). **`sha256` 2 file khớp tuyệt đối** — tiêu chí DoD quan trọng nhất đã xác nhận bằng dữ liệu thật, không phải mock.

Liên quan: [phase-20](phase-20-discovery-workspace.md) đặt hàng đợi giới hạn *số video* tải cùng lúc; phase này lo *tốc độ của từng video*. Hai cái phải chốt ngân sách kết nối chung — xem mục "Ràng buộc với phase-20".

## Mục tiêu
Tải 1 video Bilibili nhanh hơn ~2,5–3 lần bằng cách chia file thành nhiều phần tải song song qua HTTP Range, và không phải tải lại từ đầu khi đứt giữa chừng.

## Khảo sát hiện trạng
`download_service.download_bilibili_video()` ([download_service.py:47](../../backend/app/services/download_service.py#L47)):
1. Lấy DASH → `video_url`, `audio_url`
2. `_stream_to_file(video_url)` — **1 kết nối duy nhất**, `aiter_bytes()` ghi thẳng ra file
3. `_stream_to_file(audio_url)` — chạy **sau khi** video xong, cũng 1 kết nối
4. `ffmpeg -c copy` ghép lại (không re-encode)

Ba điểm chậm: một kết nối cho cả file lớn; video và audio nối đuôi nhau thay vì song song; đứt ở 90% là mất sạch, tải lại từ 0 (không có resume, không có retry từng phần).

## Đo thật (2026-09-22, video Bilibili thật, mạng thật)

**CDN có hỗ trợ Range** — điều kiện tiên quyết, đã xác nhận chứ không phỏng đoán:
```
HEAD  → 200, accept-ranges: bytes, content-length: 18,787,536
GET Range: bytes=0-1023 → 206 Partial Content
        content-range: bytes 0-1023/18787536   (nhận đúng 1024 byte)
```

**Tốc độ theo số luồng** — video 95MB (`BV1T7hB6PEBm`), mỗi phép đo tải 16MB ở **một vùng byte khác nhau chưa từng chạm**, và chạy theo thứ tự 1→4→8→16→8→4→1 để loại trừ ảnh hưởng CDN cache / khởi động chậm:

| Số luồng | Tốc độ TB | So với 1 luồng |
|---|---|---|
| 1 | 1.20 MB/s | 1.00x |
| 4 | 2.01 MB/s | 1.68x |
| 8 | **3.43 MB/s** | **2.87x** |
| 16 | 2.93 MB/s | 2.45x ⚠️ *tệ hơn 8* |

Lần đo 1 luồng ở cuối (1.13 MB/s) khớp lần đầu (1.26 MB/s) ⇒ số liệu không bị lệch do thứ tự đo.

**Ba kết luận rút ra:**
1. **Điểm ngọt là 8 luồng.** 16 luồng chậm hơn 8 — thêm kết nối quá mức phản tác dụng (tranh chấp + overhead bắt tay TLS). Đừng cho chỉnh tuỳ tiện lên cao.
2. **Trần là băng thông đường truyền, không phải số luồng.** 1 kết nối được 1.2 MB/s nhưng 8 kết nối chỉ được 3.43 MB/s (0.43 MB/s mỗi kết nối), tức là đã chạm trần đường truyền. Một kết nối TCP đơn không kéo hết băng thông được (độ trễ tới CDN cao), nhiều kết nối thì kéo gần hết. **Lời hứa đúng là "chạy hết tốc độ mạng của bạn", không phải "nhanh gấp 8 lần"** — máy có đường truyền nhanh hơn sẽ lợi nhiều hơn, máy mạng yếu gần như không đổi.
3. **Mirror dự phòng chậm hơn hẳn**: `upos-sz-mirrorcosov.bilivideo.com` 8 luồng chỉ được 1.43 MB/s so với 3.43 MB/s của `upos-hz-mirrorakam.akamaized.net` (host chính). ⇒ **Không** chia các phần ra nhiều mirror để "cộng dồn băng thông" — sẽ bị mirror chậm kéo lùi. Mirror chỉ dùng khi host chính hỏng.

**URL CDN hết hạn sau 2 giờ** — query có `deadline=1790093274` và `hdnts=exp=1790093274`, đo lúc lấy về còn đúng 2.0 giờ. ⇒ Resume **không được lưu URL**, phải lưu `bvid`/`cid` rồi gọi lại `get_play_streams()` để lấy URL mới. DB đã có `platform_video_id`, `cid` lấy lại được qua `get_video_cid()`.

**Audio chiếm ~18% dung lượng** (3.9MB audio / 17.9MB video) — tải song song với video là phần thắng gần như miễn phí, không cần cơ chế gì mới.

**Ghép ffmpeg không phải nút cổ chai**: dùng `-c copy`, không re-encode ([ffmpeg.py:57](../../backend/app/adapters/ffmpeg.py#L57)). Vẫn tốn một lượt ghi lại toàn bộ dung lượng file ra đĩa, nhưng nhỏ so với thời gian tải.

## Thiết kế đề xuất

### Hàm tải mới, giữ nguyên đường cũ làm fallback
```python
async def _download_ranged(client, url, dest, *, connections=8, video_id=None, stage=None):
    # 1. HEAD: lấy content-length + accept-ranges
    # 2. Không hỗ trợ range / không biết size / size < NGƯỠNG  ->  gọi _stream_to_file cũ
    # 3. Chia [0, size) thành `connections` khoảng, pre-allocate file (f.truncate(size))
    # 4. Mỗi worker: client.stream("GET", url, headers={"Range": f"bytes={s}-{e}"})
    #    ghi bằng pwrite/seek theo offset riêng, KHÔNG giữ cả khoảng trong RAM
    # 5. progress_service.advance() cộng dồn từ mọi worker (đã là cộng dồn sẵn)
```
- **Ngưỡng bỏ qua**: file < 8MB tải 1 luồng — chia nhỏ chỉ tốn thêm bắt tay TLS.
- **`connections == 1` (mặc định) đi thẳng `_stream_to_file` cũ**, không qua đường chia phần: một "phần" phủ cả file thì y hệt luồng đơn nhưng thêm một request HEAD và thêm rủi ro. Nhờ vậy cấu hình mặc định chạy đúng code đã chạy ổn định lâu nay.
- **Luôn giữ nhánh fallback**: nếu HEAD không trả `accept-ranges: bytes`, hoặc GET Range trả 200 thay vì 206 (một số CDN lờ header Range và trả cả file), phải quay về luồng đơn — nếu không sẽ ghi đè lung tung tạo file hỏng âm thầm.
- **Ghi file**: mở `r+b` một lần rồi mỗi worker `seek()` tới offset của mình. Không dùng N file part rồi nối lại — tốn gấp đôi dung lượng đĩa và thêm một lượt đọc/ghi toàn bộ file.

### Song song hoá video + audio
```python
await asyncio.gather(
    _download_ranged(http, video_url, video_tmp, stage="video", ...),
    _download_ranged(http, audio_url, audio_tmp, stage="audio", ...),
)
```
Lưu ý: `progress_service.set_stage()` hiện giả định các giai đoạn nối tiếp nhau ("video" rồi "audio"). Chạy song song thì hai stage chồng nhau — phải đổi sang **một stage "đang tải" duy nhất với tổng dung lượng = video + audio**, nếu không thanh % sẽ nhảy loạn. Đây là thay đổi bắt buộc đi kèm, không phải tuỳ chọn.

Với cài đặt mặc định `connections = 1`, semaphore 1 slot làm hai nhánh `gather` này tự xếp hàng — chạy tuần tự đúng như hiện nay, chỉ khác là thứ tự video/audio không còn được đảm bảo. Vì thế việc gộp stage ở trên phải làm **kể cả khi người dùng không bật nhiều luồng**.

### Tải tiếp khi đứt (resume)
Ghi file trạng thái cạnh file tạm, ví dụ `video.m4s.parts.json`:
```json
{"size": 99614720, "done": [[0, 12451839], [24903680, 37355519]]}
```
- Mỗi worker xong một khoảng thì cập nhật (ghi gộp định kỳ, không ghi mỗi chunk).
- Khi tải lại: lấy URL **mới** (URL cũ hết hạn sau 2h), đọc file trạng thái, chỉ tải các khoảng còn thiếu.
- Xoá file trạng thái khi ghép ffmpeg xong.
- **Chốt an toàn**: chỉ resume khi `content-length` mới khớp `size` đã lưu. Bilibili có thể trả stream chất lượng khác ở lần gọi sau (`dash["video"][0]` không đảm bảo bất biến) — size lệch mà vẫn resume là ra file hỏng. Lệch thì xoá làm lại từ đầu.

### Retry từng phần
Một khoảng lỗi (timeout/5xx) thì thử lại đúng khoảng đó tối đa 3 lần với backoff, không bỏ cả file. Hết lượt mới ném lỗi lên `_run_download`.

### Số luồng do người dùng chỉnh — mặc định 1, tối đa 8 (đã chốt 2026-09-22)
Thanh trượt/ô chọn trong Cài đặt, khoảng hợp lệ **1–8**, **mặc định 1**.

- **Mặc định 1 = đúng hành vi hiện tại**, không đổi gì cho tới khi người dùng chủ động bật. Cùng triết lý với `cpu_worker_count: int = 1` đã có trong [config.py](../../backend/app/core/config.py) ("mặc định 1 để khớp hành vi hiện tại, tăng lên khi biết máy chịu được").
- **Chặn cứng ở 8** ngay trong schema (`Field(ge=1, le=8)`), không chỉ giới hạn ở giao diện — số liệu đo được cho thấy 16 luồng *chậm hơn* 8, nên cho nhập cao hơn chỉ hại người dùng.
- Đọc giá trị **lúc bắt đầu mỗi lượt tải**, không đọc lúc khởi động app — đổi cài đặt phải có tác dụng ngay với video tải tiếp theo, không bắt khởi động lại.
- Kèm dòng giải thích ngay tại chỗ chỉnh, đại ý: *"Tăng số luồng giúp tải nhanh hơn trên đường truyền tốt (đo thật: 8 luồng nhanh gấp ~2,9 lần 1 luồng). Mạng yếu hoặc hay đứt thì để 1."*

**Chưa có chỗ lưu cài đặt** — đây là cài đặt thật đầu tiên của tool. Hiện `core/config.py` chỉ đọc từ env (`BaseSettings`), không sửa được từ UI; các trang trong `features/settings/` vẫn là bản demo tiếng Anh của template shadcn-admin (Profile/Account/Appearance/Notifications/Display), chưa có trang nào của dự án. Vì vậy phase này phải dựng luôn hạ tầng nhỏ:
- Bảng `app_setting` dạng khoá-giá trị theo `user_id` (hợp với `_DEFAULT_USER_ID = 1` hiện tại, và không phải làm lại khi lên multi-tenant ở [phase-18](phase-18-auth-license-hosting.md)).
- `GET /api/settings` + `PUT /api/settings` trả/nhận cả cụm cài đặt, không phải mỗi khoá một endpoint.
- Trang "Tải xuống" trong Cài đặt — **cũng là chỗ đặt `download_max_videos` của [phase-20](phase-20-discovery-workspace.md)** (số video tải cùng lúc). Hai cài đặt này nằm cạnh nhau thì người dùng mới hiểu được quan hệ giữa chúng.
- Giá trị trong `config.py` (env) giữ làm **mặc định khi DB chưa có bản ghi**, không bỏ đi.

### Ràng buộc với phase-20 — ngân sách kết nối chung
Phase-20 cho tải tối đa **3 video cùng lúc**. Người dùng đặt 8 luồng thì tổng là **24 kết nối** — vượt xa mức 16 đã đo là *chậm hơn* 8, gần như chắc chắn làm chậm tất cả và dễ dính kiểm soát tốc độ phía Bilibili.

⇒ Số luồng người dùng chọn là **trần tổng cho toàn app**, không phải cho từng video. Cách làm đúng và đơn giản nhất: một `asyncio.Semaphore(n)` **dùng chung ở tầng kết nối**, mỗi worker range giữ 1 slot. 1 video chạy một mình dùng cả 8; 3 video chạy cùng thì tự chia nhau 8 slot đó. Không cần công thức chia phần — semaphore tự lo.

Phải nói rõ điều này ngay tại chỗ chỉnh trong UI, nếu không người dùng đặt 8 rồi tải 3 video sẽ tưởng mình đang có 24 luồng.

Trường hợp `n = 1` (mặc định): semaphore 1 slot ⇒ cả app tải tuần tự đúng như hiện nay, kể cả video và audio (xem lưu ý ở mục song song hoá bên dưới).

## Nguyên liệu cần chuẩn bị
- [x] Xác nhận CDN hỗ trợ Range (206 + `accept-ranges: bytes`) — đã đo thật.
- [x] Xác nhận điểm ngọt số luồng (8) và mức phản tác dụng (16) — đã đo thật.
- [x] Xác nhận mirror chậm hơn host chính → không chia tải nhiều mirror.
- [x] Xác nhận URL hết hạn 2h → resume lưu bvid/cid chứ không lưu URL.
- [x] **Chốt 2026-09-22**: cho người dùng chỉnh số luồng trong Cài đặt, khoảng **1–8**, **mặc định 1**.
- [x] **Chốt 2026-09-22 (tự quyết)**: hoãn resume sang phase sau — multi-connection đứng một mình đã đạt mục tiêu chính (2,87x), resume là phần rủi ro/phức tạp nhất, tách ra giữ phạm vi phase này gọn.
- [x] **Chốt 2026-09-22**: `download_max_videos` đặt cùng trang Cài đặt "Tải xuống" với `download_connections` — đã làm.

## Việc cần làm

### Hạ tầng cài đặt (mới — tool chưa có cài đặt nào lưu được từ UI)
- [x] `models/app_setting.py` — bảng khoá-giá trị `(user_id, key, value)`, `UniqueConstraint(user_id, key)`.
- [x] `services/settings_service.py` — `get_all(db, user_id)` trả về đã merge với mặc định trong `config.py`; `update(db, user_id, **patch)`.
- [x] `api/settings.py` — `GET /api/settings`, `PUT /api/settings`. Validate `download_connections` bằng `Field(ge=1, le=8)` **ở schema**.
- [x] `core/config.py` — `download_connections: int = 1` (mặc định khi DB chưa có bản ghi), `download_part_min_bytes: int = 8 * 1024 * 1024`.
- [x] Frontend: trang "Tải xuống" trong `features/settings/downloads/`. Đổi từ kế hoạch ban đầu: dùng `<select>` gốc thay vì Radix `Select` (xem "Đã làm" ở đầu file — Radix Select là component đầu tiên trong repo dính lỗi môi trường test).
- [x] `sidebar-nav` của Settings: thêm mục "Tải xuống".
### Tải song song
- [x] `download_service._probe(client, url)` — HEAD gộp lấy size + kiểm tra hỗ trợ Range trong 1 request (gộp `_probe_ranges` kế hoạch ban đầu với việc lấy size cho tổng tiến độ — đỡ 1 HEAD request thừa).
- [x] `download_service._download_stream(...)` — chia phần qua `_download_range_part`, pre-allocate, retry từng phần; fallback `_download_whole` khi không hỗ trợ/quá nhỏ/`connections<=1`.
- [x] `download_bilibili_video` → `_download_bilibili_video_slot` — `asyncio.gather` video + audio.
- [x] `progress_service` — thêm stage `"downloading"`, gộp video+audio thành 1 chặng duy nhất với tổng dung lượng, thay cho 2 chặng nối tiếp cũ.
- [x] Semaphore kết nối dùng chung toàn app (`_get_connection_slots()`, cố định `DOWNLOAD_CONNECTIONS_MAX=8`), **đọc số luồng từ cài đặt lúc bắt đầu mỗi lượt tải** trong `run_download_task`.
- [ ] Resume — **hoãn sang phase sau** (tự quyết, xem mục Nguyên liệu).
- [ ] Douyin `concurrent_fragment_downloads` — chưa làm, đúng kế hoạch "đo trước rồi hãy làm" (chưa đo).
- [x] Test: `connections=1` đi đúng đường cũ (`test_connections_1_never_sends_range_header`); file nhỏ đi đường fallback; server giả không hỗ trợ range → không tạo file hỏng; CDN "nói dối" (báo hỗ trợ Range nhưng GET trả 200) → phát hiện, rơi về 1 kết nối; một phần lỗi → retry đúng phần đó không cộng dồn progress; ghép các phần ra đúng nội dung (byte-for-byte, `sha256` khớp file 1 luồng); API từ chối ngoài khoảng `[1,8]`/`[1,10]` (Pydantic `Field(ge, le)`, verify bằng test schema + test ranh giới trong `test_settings_service.py`).

## Tiêu chí hoàn thành (Definition of Done)
- [ ] **Mặc định không đổi hành vi**: cài mới (chưa đụng vào Cài đặt) tải 1 video vẫn chạy đúng đường cũ, tốc độ không tệ đi.
- [ ] Đổi số luồng trong Cài đặt → **video tải ngay sau đó dùng đúng số luồng mới, không cần khởi động lại backend**. Đếm thật số kết nối đồng thời để xác nhận, không chỉ tin vào log.
- [ ] Đặt 8 luồng rồi tải **cùng một video thật ≥100MB**, so với 1 luồng, đo xen kẽ trong cùng khoảng thời gian. Đạt khi 8 luồng nhanh hơn **≥2x**.
- [ ] **File ra phải giống hệt bản tải 1 luồng** — so `sha256` của `video.m4s` tải theo range với bản tải tuần tự. Đây là tiêu chí quan trọng nhất: tải song song sai offset cho ra file "gần đúng", ffmpeg vẫn ghép được, hỏng chỉ lộ ra khi xem giữa video.
- [ ] Video ghép xong phát được, có cả hình lẫn tiếng, đúng thời lượng.
- [ ] Ngắt mạng giữa chừng rồi bật lại → tải tiếp được, file cuối `sha256` vẫn khớp (nếu làm resume trong phase này).
- [ ] 3 video tải cùng lúc với cài đặt 8 luồng → đếm thật số kết nối đồng thời, **tổng không vượt 8** (không phải 24).
- [ ] Thanh % trên UI chạy mượt từ 0→100, không nhảy giật/lùi khi video và audio chạy song song.
- [ ] Test backend pass; không có cảnh báo mới từ linter.

## Ghi chú / rủi ro
- **Mặc định 1 nghĩa là đường code mới gần như không ai chạy.** Chọn mặc định an toàn là đúng, nhưng hệ quả là lỗi trong nhánh chia phần chỉ lộ ra ở những người tự bật lên — nhánh chạy hằng ngày vẫn là code cũ. Bù lại bằng hai việc: (1) test tự động **phải** phủ nhánh nhiều luồng, không được chỉ test nhánh mặc định; (2) khi nghiệm thu, tự tay chạy thật ở mức 8 luồng với video ≥100MB và so `sha256`, đừng chỉ chạy mức mặc định rồi kết luận "không có lỗi". Sau khi dùng thật một thời gian thấy ổn thì cân nhắc nâng mặc định lên 4.
- **Kiểm soát tốc độ phía Bilibili**: mở nhiều kết nối cùng lúc cho nhiều video là hành vi dễ bị để ý. Chưa gặp chặn trong lúc đo (8 kết nối chạy ổn), nhưng nên giữ mặc định bảo thủ và bắt lỗi 412/429 để hạ số luồng thay vì cứ thế thử lại.
- **Số đo dao động theo thời điểm**: cùng 8 luồng, hai lần đo ra 2.52 và 4.33 MB/s. Khi verify lại phải đo xen kẽ cũ/mới trong cùng một khoảng thời gian, không so kết quả đo cách nhau vài tiếng.
- **Cách đo lại** (để phiên sau dựng lại được): lấy `baseUrl` từ `get_play_streams()`, `HEAD` lấy size, rồi `GET` với header `Range: bytes=<s>-<e>` cho từng cấu hình luồng, **mỗi cấu hình một vùng byte khác nhau** và chạy theo thứ tự đảo — nếu dùng lại cùng vùng byte, kết quả sẽ bị CDN cache thổi phồng (lần đo đầu chưa kiểm soát cho ra 3.46x ở 8 luồng, đo lại đúng cách chỉ còn 2.87x).
