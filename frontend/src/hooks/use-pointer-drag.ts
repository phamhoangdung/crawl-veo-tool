import { useCallback, type RefObject } from 'react'

/**
 * Drag-and-drop lifecycle shared by the drag layers on the preview frame
 * (OverlayLayer/BlurRegionLayer/ImageLayer): measures the container at `pointerdown`,
 * attaches `pointermove`/`pointerup` to `window` (so events are still received when the mouse
 * leaves the source element), removes the listeners itself when the drag ends — plus cleanup when
 * the component unmounts midway through a drag (e.g. the user switches tab while dragging),
 * which the 3 hand-written versions before all missed.
 *
 * It does not try to also merge the coordinate formulas (fraction [0,1] vs real pixels) because
 * each place really differs — only the identically repeated lifecycle part is merged.
 */
export function usePointerDrag(containerRef: RefObject<HTMLElement | null>) {
  return useCallback(
    (onMove: (dxPx: number, dyPx: number, rect: DOMRect) => void, onEnd?: () => void) =>
      (e: React.PointerEvent) => {
        e.stopPropagation()
        const rect = containerRef.current?.getBoundingClientRect()
        if (!rect || rect.width === 0 || rect.height === 0) return
        const startX = e.clientX
        const startY = e.clientY

        function handleMove(moveEvent: PointerEvent) {
          onMove(moveEvent.clientX - startX, moveEvent.clientY - startY, rect!)
        }
        function handleUp() {
          window.removeEventListener('pointermove', handleMove)
          window.removeEventListener('pointerup', handleUp)
          onEnd?.()
        }
        window.addEventListener('pointermove', handleMove)
        window.addEventListener('pointerup', handleUp)
      },
    [containerRef]
  )
}
