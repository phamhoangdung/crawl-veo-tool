# Crawl Video Tool

Tool cá nhân: nhập từ khoá/chủ đề → crawl và tải video từ Bilibili, Douyin (không dính watermark) → dịch và lồng tiếng bằng AI (đa nhà cung cấp, tự nhập API key), hoặc tự nhập kịch bản để tool gen giọng đọc. Xuất kèm phụ đề song ngữ.

## Kiến trúc chốt
- Web app chạy local: backend Python (FastAPI) + web UI, không phải desktop app hay CLI thuần.
- Đa nhà cung cấp AI ngay từ đầu (OpenAI, Google, ElevenLabs, Azure, DeepL, Edge-TTS...), chọn provider theo từng tác vụ.
- Lồng tiếng có tách và giữ nhạc nền gốc (không xoá sạch track âm thanh).
- Đầu ra: vừa lồng tiếng vừa phụ đề song ngữ (.srt gốc + dịch), có tuỳ chọn burn-in.

Kiến trúc/tech stack đầy đủ: Backend Python/FastAPI + SQLite(WAL) + ProcessPoolExecutor→Celery/Redis khi cần; Frontend React+Vite+TS+Tailwind+shadcn/ui trên khung [satnaing/shadcn-admin](https://github.com/satnaing/shadcn-admin). Chi tiết module, rủi ro kiến trúc, roadmap gốc: xem [docs/overview/plan.md](docs/overview/plan.md) — **chỉ mở file này khi cần đối chiếu kiến trúc tổng thể hoặc lý do đằng sau 1 quyết định, KHÔNG đọc lại mỗi phiên.**

Cả 3 gate ban đầu đã chốt: Bilibili trước, cặp ngôn ngữ Trung → Việt, dùng cá nhân trước rồi mới đóng gói bán sau (chi tiết + ảnh hưởng kiến trúc ở docs/overview/plan.md phần Context).

**Hướng phân phối khi thương mại hoá (chốt 2026-09-07, tạm thời — có thể đổi lại)**: ưu tiên đóng gói **desktop app** (Tauri + PyInstaller sidecar, xem [docs/phases/phase-12-desktop-packaging.md](docs/phases/phase-12-desktop-packaging.md)), tạm gác hướng host multi-tenant SaaS/bán license qua web — lý do (chi phí compute Whisper/Demucs, rủi ro pháp lý khi host nội dung re-up cho nhiều người lạ) ở [docs/scale-reup-features/plan.md](docs/scale-reup-features/plan.md).

**Chạy dự án**: copy root `.env.example` → `.env`, điền `MASTER_KEY`, rồi `npm install` (1 lần) + `npm run dev` ở root — tự sync env vào `backend/.env`/`frontend/.env` và chạy cả backend (:8000) + frontend (:5173) cùng lúc. Chi tiết ở [docs/phases/phase-0-scaffolding.md](docs/phases/phase-0-scaffolding.md) mục "Cách chạy dự án". Lưu ý: root dùng npm (chỉ điều phối), `frontend/` dùng pnpm — không lẫn lộn.

**Coding conventions**: xem [docs/conventions.md](docs/conventions.md) (kiến trúc phân lớp backend, quy tắc frontend, git/review). Skill hỗ trợ code chất lượng cao đã cài global: `vercel-react-best-practices` (React/TS, chính chủ Vercel, 692K+ installs) — dùng skill này khi viết code React. Backend Python/FastAPI không có skill tương đương đủ tin cậy trên skills.sh, quy tắc viết thủ công trong conventions.md. Sau mỗi phase, chạy `/code-review` (built-in) trước khi đánh dấu hoàn thành.

## Quy tắc làm việc tiết kiệm token (nhiều phiên)
Dự án này chạy qua nhiều phiên làm việc riêng biệt, cần tiết kiệm token vì ngân sách có giới hạn. Áp dụng các quy tắc sau:

1. **Đầu phiên chỉ đọc**: CLAUDE.md này + file phase đang làm trong `docs/phases/phase-N-*.md`. KHÔNG đọc lại toàn bộ `docs/overview/plan.md` hay các phase khác trừ khi thực sự cần đối chiếu.
2. **Không dò lại thứ đã ghi sẵn**: đường dẫn file, cấu trúc thư mục, endpoint đã xác nhận... đều đã có trong file phase tương ứng (mục "Nguyên liệu"). Đọc trực tiếp bằng Read/Glob, không cần Explore agent hay search lại nếu file phase đã ghi rõ.
3. **Một phase ≈ một phiên làm việc** (phase lớn có thể cần 2-3 phiên, nhưng không gộp nhiều phase vào 1 phiên) — giữ context mỗi phiên nhỏ và tập trung.
4. **Chuẩn bị nguyên liệu trước khi code**: mỗi file phase có mục "Nguyên liệu cần chuẩn bị trước khi bắt đầu" — hoàn thành checklist này (API key, cookie, video mẫu, quyết định kỹ thuật nhỏ...) TRƯỚC khi vào phiên code, để phiên code không phải dừng giữa chừng đi research/hỏi lại.
5. **Cập nhật checklist ngay khi xong việc**: tick `[x]` trong file phase ngay sau khi hoàn thành, và ghi quyết định/vướng mắc phát sinh vào mục "Ghi chú phát sinh" của phase đó — để phiên sau đọc file là biết trạng thái, không cần chạy `git log` hay đọc lại code để suy luận.
6. **Tránh lặp lại thao tác vô ích**: không chạy lại cùng 1 lệnh/search nhiều lần trong 1 phiên nếu kết quả không đổi; không đọc lại 1 file vừa mới Edit/Write (đã có trong context).
7. **Khi xong 1 phase**: cập nhật cột Trạng thái trong bảng dưới, tổng kết ngắn gọn (vài dòng) thay đổi/quyết định phát sinh vào file phase đó — không cần thuật lại toàn bộ hội thoại.

## Bảng phase thực thi (đọc file phase hiện tại, không cần đọc hết)

| Phase | File | Trạng thái |
|---|---|---|
| 0. Scaffolding (backend+frontend khung) | [docs/phases/phase-0-scaffolding.md](docs/phases/phase-0-scaffolding.md) | **Hoàn thành** |
| 1. Crawl & Trend Discovery (Bilibili) | [docs/phases/phase-1-crawl-bilibili.md](docs/phases/phase-1-crawl-bilibili.md) | **Xong** (trừ batch queue concurrency, không cấp thiết) |
| 2. AI Pipeline MVP (1 provider) | [docs/phases/phase-2-ai-pipeline-mvp.md](docs/phases/phase-2-ai-pipeline-mvp.md) | **Xong** — verify end-to-end video thật |
| 3. Multi-provider + Douyin | [docs/phases/phase-3-multiprovider-douyin.md](docs/phases/phase-3-multiprovider-douyin.md) | Một phần — cost estimate xong, Douyin cần cookie thật của bạn để test tiếp |
| 4. Audio quality (tách nhạc nền) + video dài | [docs/phases/phase-4-audio-quality.md](docs/phases/phase-4-audio-quality.md) | Phần lõi xong & verify thật — chunking video dài chưa làm (thiếu video mẫu) |
| 5. Phụ đề song ngữ + Thư viện | [docs/phases/phase-5-subtitles-library.md](docs/phases/phase-5-subtitles-library.md) | **Xong & verify thật** (trừ cảnh báo hardsub, thiếu video mẫu) |
| 6. Hardening & Ops | [docs/phases/phase-6-hardening-ops.md](docs/phases/phase-6-hardening-ops.md) | Phần cốt lõi xong & verify thật (storage cleanup, health-check, SETUP.md) |
| 7. Đóng gói để bán (tương lai) | [docs/phases/phase-7-productization.md](docs/phases/phase-7-productization.md) | Ý tưởng, chưa lên kế hoạch |
| 8. AI Account Pool (nhiều key/provider, failover, n8n orchestrator) | [docs/phases/phase-8-ai-account-pool.md](docs/phases/phase-8-ai-account-pool.md) | **Phần lõi xong** & verify qua test suite (127 test) + DB thật — chưa verify qua HTTP thật (xem Ghi chú trong phase) |
| 9. Compliance & value-add cho re-up | [docs/phases/phase-9-reup-compliance.md](docs/phases/phase-9-reup-compliance.md) | **Xong & verify thật** — logo/watermark/intro/outro/nhạc nền + kho asset + UI chọn file + metadata SEO; còn thiếu source ledger |
| 10. Video kể chuyện (script + TTS + video nền) | [docs/phases/phase-10-story-videos.md](docs/phases/phase-10-story-videos.md) | Chưa bắt đầu — cần chốt hướng kịch bản; cần video nền mẫu (chưa có) |
| 11. Clip ngắn TikTok + cross-post | [docs/phases/phase-11-shorts-crosspost.md](docs/phases/phase-11-shorts-crosspost.md) | **Phần cắt clip xong & verify thật** (ffmpeg thật) — cross-post qua API chưa làm (ngoài phạm vi, xem Ghi chú) |
| 12. Đóng gói Desktop App (Tauri + PyInstaller) | [docs/phases/phase-12-desktop-packaging.md](docs/phases/phase-12-desktop-packaging.md) | **Cơ chế lõi xong & verify thật** (sidecar spawn/tắt, MASTER_KEY/storage đúng chỗ) — còn thiếu `tauri build` ra installer thật |
| 13. Trình chỉnh sửa timeline (AI gợi ý + kéo-thả) | [docs/phases/phase-13-timeline-editor.md](docs/phases/phase-13-timeline-editor.md) | **Xong & verify thật** (ffmpeg thật, DB thật, browser thật) — 9/10/11 giờ dùng chung editor này |

## Quy ước tài liệu (module/nghiên cứu, khác với phase thực thi ở trên)
Mỗi nhiệm vụ/module lớn có một thư mục riêng trong `docs/`, chứa `research.md`/`plan.md` của nhiệm vụ đó — dùng cho tài liệu tham khảo/kiến trúc, không phải checklist thực thi (đó là việc của `docs/phases/`). Khi cần thêm tài liệu module mới: tạo `docs/<ten-nhiem-vu>/`, thêm file, rồi thêm dòng vào bảng dưới.

| Nhiệm vụ | Thư mục |
|---|---|
| Tổng quan & kiến trúc toàn bộ tool | [docs/overview/plan.md](docs/overview/plan.md) |
| Mở rộng re-up quy mô lớn (compliance YouTube, video kể chuyện, clip TikTok, AI Account Pool) | [docs/scale-reup-features/plan.md](docs/scale-reup-features/plan.md) |
