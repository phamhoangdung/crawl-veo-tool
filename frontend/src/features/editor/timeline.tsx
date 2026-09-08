import { useEffect, useRef } from 'react'
import { Image as ImageIcon, Music2, Type, Video as VideoIcon } from 'lucide-react'
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
const RULER_HEIGHT = 20
/** Bề rộng cột nhãn track — playhead phải bù khoảng này để thẳng hàng với clip. */
const LABEL_WIDTH = 96

function formatTick(seconds: number) {
  const m = Math.floor(seconds / 60)
  const sec = Math.floor(seconds % 60)
  return m > 0 ? `${m}:${sec.toString().padStart(2, '0')}` : `${sec}s`
}
const TRACK_ICON: Record<TimelineTrack['type'], typeof VideoIcon> = {
  video: VideoIcon,
  audio: Music2,
  overlay: Type,
  image: ImageIcon,
}
const TRACK_COLOR: Record<TimelineTrack['type'], string> = {
  video: 'bg-blue-500/80 border-blue-600',
  audio: 'bg-emerald-500/80 border-emerald-600',
  overlay: 'bg-amber-500/80 border-amber-600',
  image: 'bg-fuchsia-500/80 border-fuchsia-600',
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
  const requestSeek = useEditorStore((s) => s.requestSeek)
  const pxPerSecond = useEditorStore((s) => s.pxPerSecond)
  const updateClip = useEditorStore((s) => s.updateClip)
  const dragRef = useRef<{ mode: DragMode; startX: number; original: TimelineClip } | null>(null)

  // Listener kéo gắn 1 lần nên không thấy pxPerSecond mới; đồng bộ qua ref để
  // zoom giữa lúc kéo vẫn tính đúng khoảng cách.
  const pxPerSecondRef = useRef(pxPerSecond)
  useEffect(() => {
    pxPerSecondRef.current = pxPerSecond
  }, [pxPerSecond])

  // 1 listener ổn định gắn 1 lần (không tạo closure mới mỗi lần render) — tránh
  // pattern "factory trả về handler" mà react-hooks/refs coi là truy cập ref lúc
  // render (dù thực chất handler chỉ chạy khi có sự kiện chuột thật).
  useEffect(() => {
    function onMove(e: PointerEvent) {
      const drag = dragRef.current
      if (!drag) return
      const deltaSeconds = pxToSeconds(e.clientX - drag.startX, pxPerSecondRef.current)
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

  /** Chọn clip đồng thời tua video tới đầu clip đó, để xem ngay đang sửa đoạn nào. */
  function selectAndSeek() {
    select({ trackIndex, clipIndex })
    requestSeek(start)
  }

  function handlePointerDown(e: React.PointerEvent<HTMLElement>) {
    e.stopPropagation()
    const mode = (e.currentTarget.dataset.dragMode as DragMode | undefined) ?? 'move'
    selectAndSeek()
    dragRef.current = { mode, startX: e.clientX, original: clip }
  }

  // Logo hiện suốt video (không có start/end) thì không kéo được: kéo sẽ tạo ra
  // mốc thời gian mà người dùng không hề yêu cầu.
  const isFullSpanImage = track.type === 'image' && (clip.start == null || clip.end == null)
  const canMove = track.type !== 'video' && !isFullSpanImage

  return (
    <div
      data-testid={`clip-${trackIndex}-${clipIndex}`}
      data-drag-mode='move'
      className={cn(
        'absolute top-1 flex h-[calc(100%-8px)] items-center overflow-hidden rounded border px-1 text-[10px] text-white select-none',
        TRACK_COLOR[track.type],
        selected && 'ring-2 ring-primary ring-offset-1'
      )}
      style={{
        left: secondsToPx(start, pxPerSecond),
        width: Math.max(8, secondsToPx(end - start, pxPerSecond)),
      }}
      onPointerDown={canMove ? handlePointerDown : selectAndSeek}
    >
      {waveformPeaks && waveformPeaks.length > 0 && (
        <WaveformCanvas
          peaks={waveformPeaks}
          width={secondsToPx(end - start, pxPerSecond)}
          height={TRACK_HEIGHT - 8}
        />
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
  /** Giây đang phát ở preview — vẽ vạch playhead. */
  currentTime?: number
}

export function Timeline({ waveformPeaks, currentTime = 0 }: TimelineProps) {
  const operations = useEditorStore((s) => s.operations)
  const clearSelection = useEditorStore((s) => s.clearSelection)
  const pxPerSecond = useEditorStore((s) => s.pxPerSecond)
  const requestSeek = useEditorStore((s) => s.requestSeek)

  const videoTrack = operations.tracks.find((t) => t.type === 'video')
  const firstAudioTrackIndex = operations.tracks.findIndex((t) => t.type === 'audio')
  const videoLayout = computeVideoTrackLayout(videoTrack?.clips ?? [])
  const totalDuration = Math.max(totalVideoDuration(videoTrack?.clips ?? []), 1)
  const timelineWidth = secondsToPx(totalDuration, pxPerSecond) + 40

  /** Bấm vào thước thời gian để tua tới đó. */
  function seekFromRuler(e: React.PointerEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect()
    requestSeek(Math.max(0, (e.clientX - rect.left) / pxPerSecond))
  }

  if (operations.tracks.length === 0) {
    return (
      <div className='flex h-32 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground'>
        Chưa có timeline — bấm "Dùng gợi ý AI" hoặc thêm clip để bắt đầu.
      </div>
    )
  }

  // Vạch mốc thời gian: thưa dần khi zoom out để không chi chít chữ.
  const tickStep = pxPerSecond >= 80 ? 1 : pxPerSecond >= 30 ? 5 : pxPerSecond >= 12 ? 15 : 60
  const ticks = Array.from(
    { length: Math.floor(totalDuration / tickStep) + 1 },
    (_, i) => i * tickStep
  )

  return (
    <div className='overflow-x-auto rounded-md border' onPointerDown={() => clearSelection()}>
      <div className='relative' style={{ width: timelineWidth, minWidth: '100%' }}>
        {/* Thước thời gian — bấm để tua. */}
        <div className='flex border-b bg-muted/30' style={{ height: RULER_HEIGHT }}>
          <div className='w-24 shrink-0 border-e' />
          <div
            className='relative flex-1 cursor-pointer'
            onPointerDown={(e) => {
              e.stopPropagation()
              seekFromRuler(e)
            }}
          >
            {ticks.map((t) => (
              <span
                key={t}
                className='absolute top-0 h-full border-s border-border/60 ps-1 text-[10px] leading-5 text-muted-foreground'
                style={{ left: secondsToPx(t, pxPerSecond) }}
              >
                {formatTick(t)}
              </span>
            ))}
          </div>
        </div>

        {/* Playhead phủ toàn bộ track, bỏ qua chuột để không chặn kéo clip. */}
        <div
          data-testid='playhead'
          className='pointer-events-none absolute top-0 bottom-0 z-20 w-px bg-red-500'
          style={{ left: LABEL_WIDTH + secondsToPx(currentTime, pxPerSecond) }}
        >
          <span className='absolute -start-1 top-0 size-2 rounded-full bg-red-500' />
        </div>

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
