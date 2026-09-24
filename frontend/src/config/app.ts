/**
 * Thông tin thương hiệu, tập trung một chỗ để đổi tên không phải sửa rải rác.
 */

export const APP_NAME = 'VieDub Studio'

export const APP_TAGLINE = 'Dịch & lồng tiếng video'

export const APP_DESCRIPTION =
  'Crawl video từ Bilibili, Douyin rồi dịch và lồng tiếng Việt bằng AI, xuất kèm phụ đề song ngữ.'

/** Chủ sở hữu bản chạy local này — hiển thị ở menu tài khoản. */
export const APP_OWNER = {
  name: 'DzungPH',
  email: 'phamhoangdung189@gmail.com',
  /** Chữ cái đầu dùng cho avatar khi không có ảnh. */
  initials: 'DP',
} as const

/** Dấu ấn tác giả hiển thị ở chân sidebar. */
export const APP_CREDIT = 'Deoz'

/**
 * Tạm tắt lấy video của 1 kênh (dải "Video khác trong kênh" + tab xem video
 * kênh đã theo dõi): Bilibili chặn risk-control (412) gần như 100% request
 * không đăng nhập, chỉ tốn request và nhồi nhật ký. Đặt `true` để bật lại —
 * backend/route vẫn còn nguyên.
 */
export const FEATURE_CHANNEL_VIDEOS = false
