import { useCallback, type RefObject } from 'react'

/**
 * Lifecycle kéo-thả dùng chung cho các lớp kéo-thả trên khung preview
 * (OverlayLayer/BlurRegionLayer/ImageLayer): đo container lúc `pointerdown`,
 * gắn `pointermove`/`pointerup` vào `window` (để vẫn nhận sự kiện khi chuột
 * rời khỏi phần tử gốc), tự gỡ listener khi kéo xong — kèm cleanup khi
 * component unmount giữa chừng cú kéo (vd người dùng chuyển tab lúc đang kéo),
 * điều mà 3 bản tự viết tay trước đây đều bỏ sót.
 *
 * Không cố gộp luôn công thức tính toạ độ (fraction [0,1] vs pixel thật) vì
 * mỗi nơi dùng khác nhau thật sự — chỉ gộp phần lifecycle lặp lại y hệt.
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
