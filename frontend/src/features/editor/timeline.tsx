import { useEffect, useRef } from 'react'
import { Music2, Type, Video as VideoIcon } from 'lucide-react'
import type { TimelineClip, TimelineTrack } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  type DragMode,
  applyDragToClip,
  computeVideoTrackLayout,
  getClipOutputRange,
  pxToSeconds,
  secondsToPx,
  totalVideoDuration,
} from './layout'
import { useEditorStore } from './store'
import { WaveformCanvas } from './waveform-canvas'

const TRACK_HEIGHT = 44
const TRACK_ICON: Record<TimelineTrack['type'], typeof VideoIcon> = {
  video: VideoIcon,
  audio: Music2,
  overlay: Type,
}
const TRACK_COLOR: Record<TimelineTrack['type'], string> = {
  video: 'bg-blue-500/80 border-blue-600',
  audio: 'bg-emerald-500/80 border-emerald-600',
  overlay: 'bg-amber-500/80 border-amber-600',
}

function formatTime(seconds: number): string {
  const s = Math.max(0, seconds)
  const m = Math.floor(s / 60)
  const rem = (s % 60).toFixed(1)
  return `${m}:${rem.padStart(4, '0')}`
}

interface ClipBoxProps {
  track: TimelineTrack
  trackIndex: number
  clipIndex: number
  videoLayout: ReturnType<typeof computeVideoTrackLayout>
  waveformPeaks?: number[]
}

function ClipBox({ track, trackIndex, clipIndex, videoLayout, waveformPeaks }: ClipBoxProps) {
  const clip = track.clips[clipIndex]
  const { start, end } = getClipOutputRange(track, clipIndex, videoLayout)
  const selected = useEditorStore(
    (s) => s.selected?.trackIndex === trackIndex && s.selected?.clipIndex === clipIndex
  )
  const select = useEditorStore((s) => s.select)
  const updateClip = useEditorStore((s) => s.updateClip)
  const dragRef = useRef<{ mode: DragMode; startX: number; original: TimelineClip } | null>(null)

  // 1 listener ổn định gắn 1 lần (không tạo closure mới mỗi lần render) — tránh
  // pattern "factory trả về handler" mà react-hooks/refs coi là truy cập ref lúc
  // render (dù thực chất handler chỉ chạy khi có sự kiện chuột thật).
  useEffect(() => {
    function onMove(e: PointerEvent) {
      const drag = dragRef.current
      if (!drag) return
      const deltaSeconds = pxToSeconds(e.clientX - drag.startX)
      const patch = applyDragToClip(drag.original, track.type, drag.mode, deltaSeconds)
      if (Object.keys(patch).length > 0) {
        updateClip(trackIndex, clipIndex, patch)
      }
    }
    function onUp() {
      dragRef.current = null
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
  }, [track.type, trackIndex, clipIndex, updateClip])

  function handlePointerDown(e: React.PointerEvent<HTMLElement>) {
    e.stopPropagation()
    const mode = (e.currentTarget.dataset.dragMode as DragMode | undefined) ?? 'move'
    select({ trackIndex, clipIndex })
    dragRef.current = { mode, startX: e.clientX, original: clip }
  }

  const canMove = track.type !== 'video'

  return (
    <div
      data-testid={`clip-${trackIndex}-${clipIndex}`}
      data-drag-mode='move'
      className={cn(
        'absolute top-1 flex h-[calc(100%-8px)] items-center overflow-hidden rounded border px-1 text-[10px] text-white select-none',
        TRACK_COLOR[track.type],
        selected && 'ring-2 ring-primary ring-offset-1'
      )}
      style={{ left: secondsToPx(start), width: Math.max(8, secondsToPx(end - start)) }}
      onPointerDown={canMove ? handlePointerDown : () => select({ trackIndex, clipIndex })}
    >
      {waveformPeaks && waveformPeaks.length > 0 && (
        <WaveformCanvas peaks={waveformPeaks} width={secondsToPx(end - start)} height={TRACK_HEIGHT - 8} />
      )}
      <div
        data-testid={`resize-start-${trackIndex}-${clipIndex}`}
        data-drag-mode='resize-start'
        className='absolute inset-y-0 left-0 w-1.5 cursor-ew-resize hover:bg-white/40'
        onPointerDown={handlePointerDown}
      />
      <span className='truncate'>{clip.text ?? clip.source?.split(/[/\\]/).pop()}</span>
      <div
        data-testid={`resize-end-${trackIndex}-${clipIndex}`}
        data-drag-mode='resize-end'
        className='absolute inset-y-0 right-0 w-1.5 cursor-ew-resize hover:bg-white/40'
        onPointerDown={handlePointerDown}
      />
    </div>
  )
}

interface TimelineProps {
  /** Waveform của track audio ĐẦU TIÊN (thường là giọng đọc) — đơn giản hoá cho
   * MVP, chưa tính waveform riêng cho từng track/clip audio khác nhau. */
  waveformPeaks?: number[]
}

export function Timeline({ waveformPeaks }: TimelineProps) {
  const operations = useEditorStore((s) => s.operations)
  const clearSelection = useEditorStore((s) => s.clearSelection)

  const videoTrack = operations.tracks.find((t) => t.type === 'video')
  const firstAudioTrackIndex = operations.tracks.findIndex((t) => t.type === 'audio')
  const videoLayout = computeVideoTrackLayout(videoTrack?.clips ?? [])
  const totalDuration = Math.max(totalVideoDuration(videoTrack?.clips ?? []), 1)
  const timelineWidth = secondsToPx(totalDuration) + 40

  if (operations.tracks.length === 0) {
    return (
      <div className='flex h-32 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground'>
        Chưa có timeline — bấm "Dùng gợi ý AI" hoặc thêm clip để bắt đầu.
      </div>
    )
  }

  return (
    <div className='overflow-x-auto rounded-md border' onPointerDown={() => clearSelection()}>
      <div style={{ width: timelineWidth, minWidth: '100%' }}>
        {operations.tracks.map((track, trackIndex) => {
          const Icon = TRACK_ICON[track.type]
          return (
            <div
              key={trackIndex}
              className='flex border-b last:border-b-0'
              style={{ height: TRACK_HEIGHT }}
            >
              <div className='flex w-24 shrink-0 items-center gap-1.5 border-e bg-muted/40 px-2 text-[11px] text-muted-foreground'>
                <Icon className='size-3.5' />
                {track.type === 'audio' ? (track.role ?? 'audio') : track.type}
              </div>
              <div className='relative flex-1' onPointerDown={(e) => e.stopPropagation()}>
                {track.clips.map((_, clipIndex) => (
                  <ClipBox
                    key={clipIndex}
                    track={track}
                    trackIndex={trackIndex}
                    clipIndex={clipIndex}
                    videoLayout={videoLayout}
                    waveformPeaks={
                      trackIndex === firstAudioTrackIndex && clipIndex === 0
                        ? waveformPeaks
                        : undefined
                    }
                  />
                ))}
              </div>
            </div>
          )
        })}
      </div>
      <p className='border-t px-2 py-1 text-[11px] text-muted-foreground'>
        Tổng thời lượng: {formatTime(totalDuration)}
      </p>
    </div>
  )
}
