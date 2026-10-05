/** Formatters shared in many places in the app — previously each page wrote the same thing
 * again (formatDuration: crawl/trending/video-detail; formatBytes:
 * video-detail/videos/dashboard), easy to drift when fixing 1 place and forgetting another. */

/** "3:05" — `null` (duration unknown) shows a dash. */
export function formatDuration(seconds: number | null): string {
  if (seconds === null) return '—'
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes}:${rest.toString().padStart(2, '0')}`
}

/** "3:05" — used when `seconds` ALWAYS has a value (e.g. while playing a video), clamps to
 * 0 if negative instead of showing a dash like `formatDuration`. */
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

/** "1.2Tr" / "45N" — view/comment counts... on video cards (Discovery screen,
 * Trend report) — previously defined separately in features/trending/format.ts
 * and duplicated once more in category-chart.tsx (Phase: component reuse review
 * 2026-09-22), now merged here with the other format functions. */
export function formatCompact(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}Tr`
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}N`
  return String(value)
}

/** "3 ngày trước" — only day-level precision is needed, no hours/minutes. */
export function formatRelativeDate(iso: string | null): string | null {
  if (!iso) return null
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  if (days <= 0) return 'Hôm nay'
  if (days === 1) return 'Hôm qua'
  if (days < 30) return `${days} ngày trước`
  const months = Math.floor(days / 30)
  return `${months} tháng trước`
}
