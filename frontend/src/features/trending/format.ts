/** Định dạng dùng chung cho card video ở trang Trending — cả Bilibili lẫn YouTube. */

export function formatCompact(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}Tr`
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}N`
  return String(value)
}

/** "3 ngày trước" — chỉ cần độ chính xác cỡ ngày, không cần giờ/phút. */
export function formatRelativeDate(iso: string | null) {
  if (!iso) return null
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  if (days <= 0) return 'Hôm nay'
  if (days === 1) return 'Hôm qua'
  if (days < 30) return `${days} ngày trước`
  const months = Math.floor(days / 30)
  return `${months} tháng trước`
}
