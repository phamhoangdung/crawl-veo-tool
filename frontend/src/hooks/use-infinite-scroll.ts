import { useEffect, useRef, useState } from 'react'

/**
 * Call `onReachEnd` when the sentinel element enters the viewport.
 *
 * Returns a callback ref to attach to an element placed at the end of the list. Uses
 * IntersectionObserver instead of listening to scroll events to avoid running the handler on every
 * frame.
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
  // Use state (not a ref) so the effect re-runs when the sentinel attaches to the DOM —
  // on the first render, the effect runs before the ref has a value.
  const [sentinel, setSentinel] = useState<HTMLDivElement | null>(null)

  // Keep the callback in a ref so the observer does not have to be recreated on every render.
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
