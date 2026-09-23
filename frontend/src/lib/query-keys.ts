/** Query key dùng chung giữa trang và `BootGate` (prefetch) — lệch key là cache không khớp. */
export const CATEGORIES_QUERY_KEY = [
  'trending',
  'bilibili',
  'categories',
] as const
export const FOLLOWED_CATEGORIES_QUERY_KEY = [
  'trending',
  'bilibili',
  'followed',
] as const
