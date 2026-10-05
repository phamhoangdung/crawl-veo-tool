import { useRef } from 'react'
import { usePointerDrag } from '@/hooks/use-pointer-drag'
import { useEditorStore } from './store'

/**
 * Drag-and-drop logo/watermark box on the preview frame, similar to `OverlayLayer` but
 * for the "image" track. `x`/`y` are the CENTER coordinates of the image as ratios [0,1] — matching the
 * backend formula (`main_w*x-overlay_w/2`), `width` is the width as a frame
 * ratio, drag the bottom-right corner to change it.
 */
export function ImageLayer({ currentTime }: { currentTime: number }) {
  // Subscribe only to the "image" track — see the explanation in OverlayLayer (same
  // reason, same approach).
  const trackIndex = useEditorStore((s) =>
    s.operations.tracks.findIndex((t) => t.type === 'image')
  )
  const track = useEditorStore((s) => s.operations.tracks.find((t) => t.type === 'image') ?? null)
  const updateClipDuringGesture = useEditorStore((s) => s.updateClipDuringGesture)
  const beginGesture = useEditorStore((s) => s.beginGesture)
  const endGesture = useEditorStore((s) => s.endGesture)
  const containerRef = useRef<HTMLDivElement>(null)
  const startDrag = usePointerDrag(containerRef)

  if (!track) return null

  function beginMove(clipIndex: number, originX: number, originY: number) {
    const handlePointerDown = startDrag((dxPx, dyPx, rect) => {
      updateClipDuringGesture(trackIndex, clipIndex, {
        x: Math.min(1, Math.max(0, originX + dxPx / rect.width)),
        y: Math.min(1, Math.max(0, originY + dyPx / rect.height)),
      })
    }, endGesture)

    // `beginGesture` must run when the pointerdown REALLY happens, not when the
    // JSX calls `beginMove(...)` to build the handler (that happens on every render).
    return (e: React.PointerEvent) => {
      beginGesture()
      handlePointerDown(e)
    }
  }

  function beginResize(clipIndex: number, originWidth: number) {
    const handlePointerDown = startDrag((dxPx, _dyPx, rect) => {
      updateClipDuringGesture(trackIndex, clipIndex, {
        width: Math.min(1, Math.max(0.03, originWidth + dxPx / rect.width)),
      })
    }, endGesture)

    return (e: React.PointerEvent) => {
      beginGesture()
      handlePointerDown(e)
    }
  }

  return (
    <div ref={containerRef} className='pointer-events-none absolute inset-0 overflow-hidden'>
      {track.clips.map((clip, clipIndex) => {
        const hasRange = clip.start != null && clip.end != null
        if (hasRange && (currentTime < clip.start! || currentTime > clip.end!))
          return null

        const x = clip.x ?? 0.9
        const y = clip.y ?? 0.1
        const width = clip.width ?? 0.15

        return (
          <div
            key={clipIndex}
            data-testid={`image-box-${clipIndex}`}
            className='pointer-events-auto absolute -translate-x-1/2 -translate-y-1/2 cursor-move rounded border-2 border-dashed border-sky-400 bg-sky-400/10'
            style={{
              left: `${x * 100}%`,
              top: `${y * 100}%`,
              width: `${width * 100}%`,
              // The real ratio is only known at render time (depends on the source image) — a
              // square frame is close enough for drag-and-drop, no pixel accuracy needed.
              aspectRatio: '1',
              opacity: clip.opacity ?? 1,
            }}
            onPointerDown={beginMove(clipIndex, x, y)}
          >
            <div
              data-testid={`image-resize-${clipIndex}`}
              className='absolute -right-1.5 -bottom-1.5 size-3 cursor-nwse-resize rounded-full border border-background bg-sky-400'
              onPointerDown={beginResize(clipIndex, width)}
            />
          </div>
        )
      })}
    </div>
  )
}
