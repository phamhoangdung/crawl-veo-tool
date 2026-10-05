import { useRef } from 'react'
import { usePointerDrag } from '@/hooks/use-pointer-drag'
import { asTimed } from './layout'
import { useEditorStore } from './store'

interface OverlayLayerProps {
  currentTime: number
}

/**
 * Drag-and-drop text overlay box on the video preview frame. `x`/`y` are the CENTER coordinates of the text
 * as ratios [0,1] — matching exactly the formula the backend uses when rendering (drawtext
 * `x=w*fx-text_w/2`), so the preview position and the render match.
 */
export function OverlayLayer({ currentTime }: OverlayLayerProps) {
  // Subscribe only to the "overlay" track — previously it took all of `s.operations`, making
  // this component re-render whenever ANY track changed (e.g. dragging a watermark),
  // though it has nothing to do with the text overlay. `mapTrack` in the store keeps the
  // reference of unchanged tracks so Zustand's default comparison (Object.is)
  // is still right — if the "overlay" track is unchanged it does not re-render, with no need for
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

    // `beginGesture` must run when the pointerdown REALLY happens, not when the
    // JSX calls `beginDrag(...)` to build the handler (that happens on every render).
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
