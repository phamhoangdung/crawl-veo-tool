import { useState } from 'react'
import { API_BASE_URL } from '@/lib/api'
import { cn } from '@/lib/utils'

/**
 * Bilibili trả cover_url dạng `http://`. Ép sang https để không bị chặn
 * mixed-content khi trang chạy qua HTTPS; CDN của họ phục vụ cả hai.
 */
function toHttps(url: string) {
  return url.startsWith('http://') ? `https://${url.slice('http://'.length)}` : url
}

/**
 * Ảnh cover Bilibili tải thẳng được nhờ referrerPolicy="no-referrer" (CDN chặn
 * hotlink theo Referer: gửi kèm localhost sẽ bị 403). Nếu vẫn bị chặn, đổi sang
 * proxy của backend — nơi đặt được Referer hợp lệ.
 */
export function CoverImage({
  src,
  className,
}: {
  src: string | null
  className?: string
}) {
  const [useProxy, setUseProxy] = useState(false)

  if (!src) {
    return <div className={cn('aspect-video bg-muted', className)} />
  }

  const directUrl = toHttps(src)

  return (
    <img
      src={
        useProxy
          ? `${API_BASE_URL}/api/image?url=${encodeURIComponent(directUrl)}`
          : directUrl
      }
      alt=''
      referrerPolicy='no-referrer'
      loading='lazy'
      onError={() => setUseProxy(true)}
      className={cn('aspect-video bg-muted object-cover', className)}
    />
  )
}
