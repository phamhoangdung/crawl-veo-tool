/**
 * Brand info, kept in one place so renaming does not mean editing scattered spots.
 */

export const APP_NAME = 'VieDub Studio'

export const APP_TAGLINE = 'Dịch & lồng tiếng video'

export const APP_DESCRIPTION =
  'Crawl video từ Bilibili, Douyin rồi dịch và lồng tiếng Việt bằng AI, xuất kèm phụ đề song ngữ.'

/** Owner of this local build — shown in the account menu. */
export const APP_OWNER = {
  name: 'DzungPH',
  email: 'phamhoangdung189@gmail.com',
  /** Initial letter used for the avatar when there is no image. */
  initials: 'DP',
} as const

/** Author credit shown at the foot of the sidebar. */
export const APP_CREDIT = 'Deoz'

/**
 * Temporarily turn off fetching a channel's videos (the "Other videos in the channel" strip + the tab viewing
 * followed channels' videos): Bilibili risk control (412) blocks almost 100% of
 * logged-out requests, only costing requests and stuffing the log. Set `true` to turn it back on —
 * the backend/route are still intact.
 */
export const FEATURE_CHANNEL_VIDEOS = false
