import { useRef } from 'react'
import { X } from 'lucide-react'
import type { TimelineClip } from '@/lib/api'
import { useEditorStore } from './store'

/** Kéo mép nào — 'move' là kéo cả khung. */
type Handle = 'move' | 'se'

/**
 * Vùng làm mờ kéo-thả trên khung preview, để che logo hoặc phụ đề tiếng Trung
 * có sẵn trong video gốc.
 *
 * Toạ độ theo TỈ LỆ khung hình [0,1] — khớp đúng công thức backend dùng khi
 * render (`crop=iw*w:ih*h:iw*x:ih*y`), nên vùng che xem trước đúng bằng vùng che
 * trong bản render, dù preview bị scale nhỏ lại.
 */
export function BlurRegionLayer({ currentTime }: { currentTime: number }) {
  const operations = useEditorStore((s) => s.operations)
  const updateClip = useEditorStore((s) => s.updateClip)
  const removeClip = useEditorStore((s) => s.removeClip)
  const containerRef = useRef<HTMLDivElement>(null)

  const trackIndex = operations.tracks.findIndex((t) => t.type === 'blur')
  const track = trackIndex >= 0 ? operations.tracks[trackIndex] : null

  if (!track) return null

  function beginDrag(clipIndex: number, clip: TimelineClip, handle: Handle) {
    return (e: React.PointerEvent) => {
      e.stopPropagation()
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect || rect.width === 0 || rect.height === 0) return

      const startX = e.clientX
      const startY = e.clientY
      const origin = {
        x: clip.x ?? 0,
        y: clip.y ?? 0,
        width: clip.width ?? 0.2,
        height: clip.height ?? 0.1,
      }

      const onMove = (ev: PointerEvent) => {
        const dx = (ev.clientX - startX) / rect.width
        const dy = (ev.clientY - startY) / rect.height

        if (handle === 'move') {
          updateClip(trackIndex, clipIndex, {
            // Chặn ở mép: vùng che tràn ra ngoài khung làm ffmpeg crop lỗi.
            x: Math.min(1 - origin.width, Math.max(0, origin.x + dx)),
            y: Math.min(1 - origin.height, Math.max(0, origin.y + dy)),
          })
          return
        }

        updateClip(trackIndex, clipIndex, {
          width: Math.min(1 - origin.x, Math.max(0.02, origin.width + dx)),
          height: Math.min(1 - origin.y, Math.max(0.02, origin.height + dy)),
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
    <div
      ref={containerRef}
      className='pointer-events-none absolute inset-0 overflow-hidden'
    >
      {track.clips.map((clip, clipIndex) => {
        // Không có mốc thời gian = che suốt video.
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
