/** Định dạng dùng chung nhiều nơi trong app — trước đây mỗi trang tự viết lại
 * y hệt (formatDuration: crawl/trending/video-detail; formatBytes:
 * video-detail/videos/dashboard), dễ lệch khi sửa 1 chỗ quên chỗ khác. */

/** "3:05" — `null` (chưa biết thời lượng) hiện dấu gạch ngang. */
export function formatDuration(seconds: number | null): string {
  if (seconds === null) return '—'
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes}:${rest.toString().padStart(2, '0')}`
}

/** "3:05" — dùng khi `seconds` LUÔN có giá trị (vd đang phát video), tự kẹp về
 * 0 nếu âm thay vì hiện dấu gạch ngang như `formatDuration`. */
export function formatTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

/** "1.5 MB" */
export function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

/** "1.2Tr" / "45N" — số lượt xem/bình luận... trên card video (màn Khám phá,
 * Báo cáo xu hướng) — trước đây định nghĩa riêng ở features/trending/format.ts
 * và bị trùng lặp lần nữa ở category-chart.tsx (Phase: rà soát tái sử dụng
 * component 2026-09-22), giờ gộp về đây cùng các hàm format khác. */
export function formatCompact(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}Tr`
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}N`
  return String(value)
}

/** "3 ngày trước" — chỉ cần độ chính xác cỡ ngày, không cần giờ/phút. */
export function formatRelativeDate(iso: string | null): string | null {
  if (!iso) return null
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  if (days <= 0) return 'Hôm nay'
  if (days === 1) return 'Hôm qua'
  if (days < 30) return `${days} ngày trước`
  const months = Math.floor(days / 30)
  return `${months} tháng trước`
}
