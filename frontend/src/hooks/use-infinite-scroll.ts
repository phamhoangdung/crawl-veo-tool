import { useEffect, useRef, useState } from 'react'

/**
 * Gọi `onReachEnd` khi phần tử sentinel lọt vào tầm nhìn.
 *
 * Trả về callback ref để gắn vào một phần tử đặt cuối danh sách. Dùng
 * IntersectionObserver thay vì nghe sự kiện scroll để tránh chạy handler mỗi
 * khung hình.
 */
export function useInfiniteScroll({
  enabled,
  onReachEnd,
  rootMargin = '400px',
}: {
  enabled: boolean
  onReachEnd: () => void
  rootMargin?: string
}) {
  // Dùng state (không phải ref) để effect chạy lại khi sentinel gắn vào DOM —
  // ở lần render đầu, effect chạy trước khi ref kịp có giá trị.
  const [sentinel, setSentinel] = useState<HTMLDivElement | null>(null)

  // Giữ callback trong ref để observer không phải tạo lại mỗi lần render.
  const onReachEndRef = useRef(onReachEnd)
  useEffect(() => {
    onReachEndRef.current = onReachEnd
  }, [onReachEnd])

  useEffect(() => {
    if (!sentinel || !enabled) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          onReachEndRef.current()
        }
      },
      { rootMargin }
    )

    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [sentinel, enabled, rootMargin])

  return setSentinel
}
