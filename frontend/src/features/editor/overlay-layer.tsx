import { useRef } from 'react'
import { usePointerDrag } from '@/hooks/use-pointer-drag'
import { asTimed } from './layout'
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
  // Chỉ subscribe đúng track "overlay" — trước đây lấy cả `s.operations` khiến
  // component này render lại mỗi khi BẤT KỲ track nào đổi (vd kéo watermark),
  // dù chẳng liên quan gì tới overlay text. `mapTrack` trong store giữ nguyên
  // reference của track không đổi nên so sánh mặc định (Object.is) của Zustand
  // vẫn đúng — track "overlay" không đổi thì không render lại, không cần
  // `useShallow`.
  const overlayTrackIndex = useEditorStore((s) =>
    s.operations.tracks.findIndex((t) => t.type === 'overlay')
  )
  const overlayTrack = useEditorStore(
    (s) => s.operations.tracks.find((t) => t.type === 'overlay') ?? null
  )
  const updateClipDuringGesture = useEditorStore((s) => s.updateClipDuringGesture)
  const beginGesture = useEditorStore((s) => s.beginGesture)
  const endGesture = useEditorStore((s) => s.endGesture)
  const containerRef = useRef<HTMLDivElement>(null)
  const startDrag = usePointerDrag(containerRef)

  if (!overlayTrack) return null

  function beginDrag(clipIndex: number, originX: number, originY: number) {
    const handlePointerDown = startDrag((dxPx, dyPx, rect) => {
      updateClipDuringGesture(overlayTrackIndex, clipIndex, {
        x: Math.min(1, Math.max(0, originX + dxPx / rect.width)),
        y: Math.min(1, Math.max(0, originY + dyPx / rect.height)),
      })
    }, endGesture)

    // `beginGesture` phải chạy lúc pointerdown THẬT sự xảy ra, không phải lúc
    // JSX gọi `beginDrag(...)` để dựng handler (chuyện đó xảy ra mỗi lần render).
    return (e: React.PointerEvent) => {
      beginGesture()
      handlePointerDown(e)
    }
  }

  return (
    <div ref={containerRef} className='pointer-events-none absolute inset-0 overflow-hidden'>
      {overlayTrack.clips.map((rawClip, clipIndex) => {
        const clip = asTimed(rawClip)
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
