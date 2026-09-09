# Thiết kế UI/UX: AI Studio (Phase 14)

Ngày: 2026-09-09. Nguyên liệu tham chiếu: `goha-screenshots/` (bố cục thật của GOHA Flow Studio), `research.md` Phần 6. Phase thực thi: [phase-14-ai-video-generation.md](../phases/phase-14-ai-video-generation.md).

Tài liệu này chốt bố cục + luồng trạng thái để phiên code không phải tự quyết giữa chừng. Không phải bản vẽ pixel-perfect — chỉ định nghĩa cấu trúc, thứ tự thao tác, và trạng thái edge case.

## Nguyên tắc thiết kế cho trang này

1. **Sidebar cấu hình bên trái, vùng làm việc bên phải** — học từ GOHA: mọi tham số (model, tỉ lệ, chất lượng, thư mục lưu, ảnh ref đang dùng) nằm cố định ở sidebar trái để không phải cuộn đi cuộn lại; vùng phải chỉ chứa nội dung đang làm (prompt + kết quả).
2. **Chi phí luôn hiện trước khi bấm** — khác hẳn dịch/TTS (rẻ), sinh video đắt ($0.10-0.60/giây). Nút hành động phải kèm số tiền ước tính, không để user bấm rồi mới biết.
3. **Không ẩn trạng thái chờ** — sinh ảnh mất 5-30s, sinh video 1-5 phút. Phải có progress rõ ràng, và cho phép rời trang mà job vẫn chạy (job chạy nền, quay lại xem được).
4. **Tuần tự nhưng không cứng nhắc** — 4 bước có thứ tự, nhưng cho phép quay lại bước trước (đổi ảnh ref, sinh lại ảnh) mà không mất kết quả đã có.
5. **Tái dùng component đã có** — `shadcn/ui` (Select, Button, Card, Dialog, Progress, Badge), pattern cost-estimate đã có ở trang Crawl/Videos. Không dựng component mới nếu tránh được.

## Bố cục tổng thể

```
┌────────────────────────────────────────────────────────────────────────────┐
│ AI Studio                                    [Pool: 2 key falai ✓]  [?]    │  ← header
├──────────────────────┬─────────────────────────────────────────────────────┤
│ CẤU HÌNH             │  ① Bộ ảnh tham chiếu ────────────────── [đã chọn ✓] │
│                      │  ② Sinh ảnh keyframe ───────────────────  [đang mở] │
│ Bộ ảnh tham chiếu    │  ┌───────────────────────────────────────────────┐  │
│ ┌──────────────────┐ │  │ Prompt (mô tả cảnh)                           │  │
│ │ ▣ sunhui_hero    │ │  │ ┌───────────────────────────────────────────┐ │  │
│ │ ▢ sunhui_sheet   │ │  │ │ @sunhui_hero Over-the-shoulder medium... │ │  │
│ │ ▢ prop_tongjang  │ │  │ └───────────────────────────────────────────┘ │  │
│ │ [+ Thêm bộ ảnh]  │ │  │ Ảnh ref sẽ dùng: [🖼][🖼][🖼]  (tự nhận từ @) │  │
│ └──────────────────┘ │  │                                               │  │
│                      │  │  Ước tính: ~$0.04    [ Sinh ảnh (4 biến thể) ]│  │
│ Model ảnh            │  └───────────────────────────────────────────────┘  │
│ [Nano Banana ▾]      │                                                     │
│                      │  Kết quả (chọn 1 để sinh video):                    │
│ Tỉ lệ                │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                   │
│ [Ngang 16:9 ▾]       │  │ ✓   │ │     │ │     │ │     │                   │
│                      │  │ img │ │ img │ │ img │ │ img │                   │
│ Số biến thể          │  └─────┘ └─────┘ └─────┘ └─────┘                   │
│ [4 ảnh ▾]            │                                                     │
│                      │  ③ Sinh video clip ──────────────────  [chờ bước ②]│
│ Chất lượng           │  ④ Xuất / ghép ────────────────────── [chờ bước ③]│
│ [Standard 1K ▾]      │                                                     │
│ ─────────────────    │                                                     │
│ Tên output (prefix)  │                                                     │
│ [EP001          ]    │                                                     │
│ → EP001_001.png      │                                                     │
└──────────────────────┴─────────────────────────────────────────────────────┘
```

Bốn bước là **accordion dọc** trong vùng phải: bước đang làm mở rộng, bước đã xong thu gọn thành 1 dòng có badge trạng thái + nút "Sửa" để mở lại, bước chưa tới bị disable (màu mờ, không click được).

## Bước ① — Chọn bộ ảnh tham chiếu

**Sidebar**: danh sách bộ ảnh (checkbox nhiều lựa chọn, mỗi dòng: tên slug + số ảnh). Bấm "+ Thêm bộ ảnh" mở Dialog:

| Field | Kiểu | Validate |
|---|---|---|
| Tên (slug) | text | bắt buộc, `^[a-z0-9_]+$`, unique — hiện lỗi inline ngay khi blur; hint: "dùng để gọi trong prompt: `@ten_ban_dat`" |
| Mô tả | textarea | optional |
| Ảnh | file upload (nhiều) | ≥1 ảnh, chỉ `.jpg/.png/.webp`, cảnh báo mềm nếu <2 ảnh ("nên có 2-4 góc để nhân vật nhất quán hơn") |

Sau khi tạo, bộ ảnh xuất hiện trong danh sách và **tự động được tick**. Vùng phải bước ① thu gọn, hiện: `Đang dùng: sunhui_hero (3 ảnh), prop_tongjang (1 ảnh)` + thumbnail grid nhỏ.

**Edge case**: chưa có bộ ảnh nào → vùng phải hiện empty state với 1 nút "Tạo bộ ảnh đầu tiên" và 1 câu giải thích ngắn tại sao cần ảnh tham chiếu (giữ nhân vật nhất quán giữa các cảnh), không phải bảng trống.

## Bước ② — Sinh ảnh keyframe

**Prompt textarea** với 2 hỗ trợ nhỏ (rẻ, giá trị cao):
- Autocomplete `@` — gõ `@` hiện dropdown các bộ ảnh đang tick để chèn nhanh, tránh sai tên slug.
- Dưới textarea: dòng "Ảnh ref sẽ dùng:" + thumbnail các ảnh được parse ra từ `@mention` trong prompt — **phản hồi tức thì**, để user thấy matching đúng trước khi tốn tiền. Nếu prompt có `@ten_khong_ton_tai` → badge đỏ cảnh báo, disable nút sinh.

**Nút hành động**: `[ Sinh ảnh (4 biến thể) — ~$0.04 ]`. Số tiền lấy từ `GET /generate/cost-estimate`, cập nhật khi đổi model/số biến thể/chất lượng ở sidebar. Nếu vượt ngưỡng đã chốt ($1/lần) → nút đổi màu cảnh báo và bấm vào mở Dialog xác nhận ("Lần sinh này ước tính $X, vượt ngưỡng $1. Tiếp tục?") thay vì chặn cứng.

**Trạng thái đang chạy**: nút chuyển thành progress (`Đang sinh... 12s`), 4 ô kết quả hiện skeleton. Cho phép "Huỷ" nếu provider hỗ trợ; nếu không, ghi rõ "không huỷ được sau khi đã gửi" trong tooltip để user không kỳ vọng sai.

**Kết quả**: lưới 4 ảnh, hover hiện nút phóng to (Dialog xem ảnh gốc). Click 1 ảnh = chọn (viền + dấu ✓). Chọn xong bước ② thu gọn, bước ③ mở ra.
- Nút "Sinh thêm 4 biến thể" (giữ nguyên prompt, tốn thêm tiền — hiện lại giá).
- Không ảnh nào ưng: sửa prompt rồi bấm sinh lại; các ảnh cũ vẫn giữ trong lịch sử phía dưới (không mất, vì đã trả tiền rồi).

## Bước ③ — Sinh video clip

```
┌───────────────────────────────────────────────────────────────┐
│ Ảnh đầu (start)          Ảnh cuối (end) — tuỳ chọn           │
│ ┌────────┐               ┌────────┐                          │
│ │ ✓ img  │      →        │   +    │  ← click chọn từ kết quả │
│ └────────┘               └────────┘     bước ② hoặc bỏ trống │
│                                                               │
│ Prompt chuyển động                                            │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ camera slowly pushes in, she turns her head...            │ │
│ └───────────────────────────────────────────────────────────┘ │
│                                                               │
│ Model video [Kling 3.0 ▾]   Thời lượng [5s ▾]                │
│                                                               │
│ ⚠ Ước tính: ~$0.50 (5s × $0.10/s)   [ Sinh video ]           │
└───────────────────────────────────────────────────────────────┘
```

- **Ảnh cuối để trống = image-to-video thường**; có ảnh cuối = frame-to-frame interpolation (kiểm soát tốt hơn, khớp cảnh trước/sau). Tooltip giải thích ngắn khác biệt, vì đây là khái niệm không hiển nhiên.
- Thời lượng ảnh hưởng giá theo tuyến tính → hiện phép tính (`5s × $0.10/s`) chứ không chỉ tổng, để user hiểu vì sao đắt.
- **Trạng thái chạy**: video mất 1-5 phút → progress bar + text "Đang sinh video (khoảng 1-5 phút)... 47s" và **banner "Có thể rời trang, job vẫn chạy"**. Khi xong: toast + (nếu tab đang mở) player hiện ngay.
- Kết quả: video player (controls đầy đủ), badge model + thời lượng + chi phí thực. Nút "Sinh lại" (tốn tiền, hiện giá) và "Dùng clip này" → bước ④.

## Bước ④ — Xuất / ghép

Ba hành động, không phải luồng tuần tự:

| Hành động | Kết quả |
|---|---|
| **Thêm vào thư viện video nền** | Gọi `background_library_service` (Phase 10) → toast "Đã thêm, dùng được ở trang Story Videos". |
| **Mở trong Timeline Editor** | Điều hướng sang Phase 13 editor với clip đã nạp sẵn — để ghép nhiều clip thành video dài. |
| **Tải file về** | Download trực tiếp. |

Dưới cùng: khối "Lịch sử phiên này" — danh sách các asset đã sinh (ảnh + video) kèm chi phí từng cái và **tổng chi phí phiên** (`Tổng đã chi: $2.34`). Đây là cảnh báo tự nhiên chống đốt tiền, hiệu quả hơn mọi warning dialog.

## Trạng thái lỗi (phải có, không để generic)

| Lỗi | Hiển thị |
|---|---|
| Chưa có key `falai` trong pool | Banner ngay đầu trang: "Chưa có API key fal.ai" + nút "Thêm key" → `/api-keys`. Disable toàn bộ nút sinh. |
| Tất cả key hết quota (429) | Toast + banner: "Cả 2 key fal.ai đều đang bị giới hạn. Thử lại sau X phút hoặc thêm key mới." (lấy cooldown từ Phase 8 pool). |
| Prompt bị provider chặn (policy) | Hiện nguyên văn lỗi provider + nút "Nhờ AI sửa prompt" (nếu đã có key LLM — tái dùng multi-provider Phase 3; nếu chưa có key thì ẩn nút, không hiện nút chết). |
| Vượt ngưỡng chi phí | Dialog xác nhận có số tiền cụ thể (không chặn cứng — user tự quyết). |
| Job fail giữa đường | Giữ nguyên prompt + ảnh đã chọn, nút "Thử lại" — **không** reset form (mất công nhập lại là lỗi UX tệ nhất ở luồng này). |
| Nhân vật không nhất quán | Không phải lỗi hệ thống, nhưng nên có hint tĩnh ở bước ①: "Nhân vật trông khác nhau giữa các clip? Thêm 2-4 góc ảnh vào bộ tham chiếu." |

## Quản lý MCP token (đặt ở `/api-keys`, không phải AI Studio)

Section riêng dưới phần pool key provider:

```
┌── MCP Access Token (cho agent ngoài: Claude Code, Codex) ──────────┐
│ Tên token: [claude-code        ]                                   │
│ Scope:  ▣ assets:read  ▣ assets:write  ▣ gen:write                │
│         ▣ jobs:read    ▣ cost:read                                 │
│                                        [ Tạo token ]               │
│                                                                    │
│ ⚠ Token chỉ hiện 1 lần — copy và lưu ngay:                        │
│ ┌────────────────────────────────────────────────┐ [Copy]          │
│ │ sk_local_a1b2c3...                             │                 │
│ └────────────────────────────────────────────────┘                 │
│                                                                    │
│ Config MCP (dán vào Claude Code):              [Copy config]       │
│ ┌────────────────────────────────────────────────┐                 │
│ │ { "mcpServers": { "crawl-veo": { ... } } }     │                 │
│ └────────────────────────────────────────────────┘                 │
│                                                                    │
│ Token đang hoạt động:                                              │
│ • claude-code · a1b2c3d4 · 5 scope · 2026-09-09      [Thu hồi]    │
└────────────────────────────────────────────────────────────────────┘
```

Điểm quan trọng: khối JSON config sinh sẵn kèm token vừa tạo (đường dẫn Python venv + `GOHA_API_BASE`-tương-đương lấy từ config runtime), có nút copy — vì tự viết config MCP bằng tay rất dễ sai đường dẫn. Sau khi rời trang/reload, token không hiện lại được nữa (chỉ còn hash), UI phải nói rõ điều đó **trước** khi user rời đi.

## Những gì cố ý KHÔNG làm ở Phase 14

- **Node-canvas kéo-thả** (kiểu Google Flow/React Flow): đã quyết định ngoài phạm vi. Form tuần tự đủ cho nhu cầu cá nhân; canvas là đầu tư frontend lớn và Timeline Editor (Phase 13) đã lo phần ghép.
- **Bảng batch nhiều dòng** (kiểu GOHA `install-01`): Phase 14 làm đơn-item trước. Nếu sau này cần batch, cấu trúc `@mention` + `output_prefix` đã sẵn sàng để mở rộng mà không phá thiết kế.
- **Cấu hình concurrency phơi ra UI** (Luồng/account, delay): chưa cần khi chạy đơn-item. Ghi lại ở research Phần 6.4 nếu sau này chạy song song nhiều job.
- **Hiển thị CPU/GPU/RAM trên header**: chỉ có ý nghĩa khi chạy model local. Phase 14 gọi API cloud (fal.ai), không cần.
