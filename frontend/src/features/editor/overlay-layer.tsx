import { useRef } from 'react'
import { useEditorStore } from './store'

interface OverlayLayerProps {
  currentTime: number
}

/**
 * Hộp overlay text kéo-thả trên khung preview video. `x`/`y` là toạ độ TÂM chữ
 * theo tỉ lệ [0,1] — khớp đúng công thức backend dùng khi render (drawtext
 * `x=w*fx-text_w/2`), để vị trí xem trước và bản render ra khớp nhau.
 */
export function OverlayLayer({ currentTime }: OverlayLayerProps) {
  const operations = useEditorStore((s) => s.operations)
  const updateClip = useEditorStore((s) => s.updateClip)
  const containerRef = useRef<HTMLDivElement>(null)

  const overlayTrackIndex = operations.tracks.findIndex((t) => t.type === 'overlay')
  const overlayTrack = overlayTrackIndex >= 0 ? operations.tracks[overlayTrackIndex] : null

  if (!overlayTrack) return null

  function beginDrag(clipIndex: number, originX: number, originY: number) {
    return (e: React.PointerEvent) => {
      e.stopPropagation()
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect || rect.width === 0 || rect.height === 0) return
      const startX = e.clientX
      const startY = e.clientY

      const onMove = (moveEvent: PointerEvent) => {
        const dx = (moveEvent.clientX - startX) / rect.width
        const dy = (moveEvent.clientY - startY) / rect.height
        updateClip(overlayTrackIndex, clipIndex, {
          x: Math.min(1, Math.max(0, originX + dx)),
          y: Math.min(1, Math.max(0, originY + dy)),
        })
      }
      const onUp = () => {
        window.removeEventListener('pointermove', onMove)
        window.removeEventListener('pointerup', onUp)
      }
      window.addEventListener('pointermove', onMove)
      window.addEventListener('pointerup', onUp)
    }
  }

  return (
    <div ref={containerRef} className='pointer-events-none absolute inset-0 overflow-hidden'>
      {overlayTrack.clips.map((clip, clipIndex) => {
        if (currentTime < clip.start || currentTime > clip.end) return null
        const x = clip.x ?? 0.5
        const y = clip.y ?? 0.9
        return (
          <div
            key={clipIndex}
            data-testid={`overlay-box-${clipIndex}`}
            className='pointer-events-auto absolute max-w-[80%] -translate-x-1/2 -translate-y-1/2 cursor-move rounded bg-black/60 px-2 py-1 text-xs whitespace-nowrap text-white select-none'
            style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
            onPointerDown={beginDrag(clipIndex, x, y)}
          >
            {clip.text}
          </div>
        )
      })}
    </div>
  )
}
