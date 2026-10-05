import { useRef } from 'react'
import { X } from 'lucide-react'
import type { TimelineClip } from '@/lib/api'
import { usePointerDrag } from '@/hooks/use-pointer-drag'
import { useEditorStore } from './store'

/** Which edge is being dragged — 'move' drags the whole box. */
type Handle = 'move' | 'se'

/**
 * Blur region drag-and-drop on the preview frame, to hide a logo or Chinese subtitles
 * already in the source video.
 *
 * Coordinates are in frame RATIOS [0,1] — matching exactly the formula the backend uses when
 * rendering (`crop=iw*w:ih*h:iw*x:ih*y`), so the preview hiding region equals the hiding region
 * in the render, even when the preview is scaled down.
 */
export function BlurRegionLayer({ currentTime }: { currentTime: number }) {
  // Subscribe only to the "blur" track — see the explanation in OverlayLayer (same
  // reason, same approach).
  const trackIndex = useEditorStore((s) =>
    s.operations.tracks.findIndex((t) => t.type === 'blur')
  )
  const track = useEditorStore((s) => s.operations.tracks.find((t) => t.type === 'blur') ?? null)
  const updateClipDuringGesture = useEditorStore((s) => s.updateClipDuringGesture)
  const beginGesture = useEditorStore((s) => s.beginGesture)
  const endGesture = useEditorStore((s) => s.endGesture)
  const removeClip = useEditorStore((s) => s.removeClip)
  const containerRef = useRef<HTMLDivElement>(null)
  const startDrag = usePointerDrag(containerRef)

  if (!track) return null

  function beginDrag(clipIndex: number, clip: TimelineClip, handle: Handle) {
    const origin = {
      x: clip.x ?? 0,
      y: clip.y ?? 0,
      width: clip.width ?? 0.2,
      height: clip.height ?? 0.1,
    }

    const handlePointerDown = startDrag((dxPx, dyPx, rect) => {
      const dx = dxPx / rect.width
      const dy = dyPx / rect.height

      if (handle === 'move') {
        updateClipDuringGesture(trackIndex, clipIndex, {
          // Clamp at the edge: a hiding region spilling outside the frame makes ffmpeg crop fail.
          x: Math.min(1 - origin.width, Math.max(0, origin.x + dx)),
          y: Math.min(1 - origin.height, Math.max(0, origin.y + dy)),
        })
        return
      }

      updateClipDuringGesture(trackIndex, clipIndex, {
        width: Math.min(1 - origin.x, Math.max(0.02, origin.width + dx)),
        height: Math.min(1 - origin.y, Math.max(0.02, origin.height + dy)),
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
    <div
      ref={containerRef}
      className='pointer-events-none absolute inset-0 overflow-hidden'
    >
      {track.clips.map((clip, clipIndex) => {
        // No time range = hide for the whole video.
        const hasRange = clip.start != null && clip.end != null
        if (hasRange && (currentTime < clip.start! || currentTime > clip.end!))
          return null

        return (
          <div
            key={clipIndex}
            data-testid={`blur-region-${clipIndex}`}
            className='pointer-events-auto absolute cursor-move border-2 border-dashed border-amber-400 bg-amber-400/20 backdrop-blur-sm'
            style={{
              left: `${(clip.x ?? 0) * 100}%`,
              top: `${(clip.y ?? 0) * 100}%`,
              width: `${(clip.width ?? 0.2) * 100}%`,
              height: `${(clip.height ?? 0.1) * 100}%`,
            }}
            onPointerDown={beginDrag(clipIndex, clip, 'move')}
          >
            <button
              type='button'
              aria-label='Xoá vùng che'
              data-testid={`blur-remove-${clipIndex}`}
              className='absolute -top-2 -right-2 rounded-full bg-destructive p-0.5 text-white'
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => removeClip(trackIndex, clipIndex)}
            >
              <X className='size-3' />
            </button>
            <div
              data-testid={`blur-resize-${clipIndex}`}
              className='absolute -right-1.5 -bottom-1.5 size-3 cursor-nwse-resize rounded-full border border-background bg-amber-400'
              onPointerDown={beginDrag(clipIndex, clip, 'se')}
            />
          </div>
        )
      })}
    </div>
  )
}
