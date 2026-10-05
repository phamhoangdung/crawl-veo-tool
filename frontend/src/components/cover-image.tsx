import { useState } from 'react'
import { API_BASE_URL } from '@/lib/api'
import { cn } from '@/lib/utils'

/**
 * Bilibili returns cover_url as `http://`. Force https so it is not blocked as
 * mixed content when the page runs over HTTPS; their CDN serves both.
 */
function toHttps(url: string) {
  return url.startsWith('http://')
    ? `https://${url.slice('http://'.length)}`
    : url
}

/**
 * Bilibili cover images can be loaded directly thanks to referrerPolicy="no-referrer" (the CDN blocks
 * hotlinking by Referer: sending localhost along gets a 403). If it is still blocked, switch to the
 * backend proxy — where a valid Referer can be set.
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

  // The cover image of a video imported from disk is served by the backend (relative path).
  if (src.startsWith('/')) {
    return (
      <img
        src={`${API_BASE_URL}${src}`}
        alt=''
        loading='lazy'
        className={cn('aspect-video bg-muted object-cover', className)}
      />
    )
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
