/** Query keys shared between pages and `BootGate` (prefetch) — a mismatched key means the cache does not match. */
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
