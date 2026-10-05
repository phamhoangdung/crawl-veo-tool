import { useEffect, useRef } from 'react'
import {
  Droplet,
  Image as ImageIcon,
  Music2,
  Type,
  Video as VideoIcon,
} from 'lucide-react'
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
/** Width of the track label column — the playhead must offset by this to line up with clips. */
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
  // The blur-region track was added in a later phase but these 2 tables were not updated —
  // a missing entry means a blur clip shows with no icon and no color.
  blur: Droplet,
}
const TRACK_COLOR: Record<TimelineTrack['type'], string> = {
  video: 'bg-blue-500/80 border-blue-600',
  audio: 'bg-emerald-500/80 border-emerald-600',
  overlay: 'bg-amber-500/80 border-amber-600',
  image: 'bg-fuchsia-500/80 border-fuchsia-600',
  blur: 'bg-slate-500/80 border-slate-600',
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
  const updateClipDuringGesture = useEditorStore((s) => s.updateClipDuringGesture)
  const beginGesture = useEditorStore((s) => s.beginGesture)
  const endGesture = useEditorStore((s) => s.endGesture)
  const dragRef = useRef<{ mode: DragMode; startX: number; original: TimelineClip } | null>(null)

  // The drag listener is attached once so it does not see the new pxPerSecond; sync via a ref so
  // zooming in the middle of a drag still computes the distance correctly.
  const pxPerSecondRef = useRef(pxPerSecond)
  useEffect(() => {
    pxPerSecondRef.current = pxPerSecond
  }, [pxPerSecond])

  // 1 stable listener attached once (no new closure created on every render) — avoids the
  // "factory returning a handler" pattern that react-hooks/refs treats as accessing a ref during
  // render (even though the handler really only runs on a real mouse event).
  useEffect(() => {
    function onMove(e: PointerEvent) {
      const drag = dragRef.current
      if (!drag) return
      const deltaSeconds = pxToSeconds(e.clientX - drag.startX, pxPerSecondRef.current)
      const patch = applyDragToClip(drag.original, track.type, drag.mode, deltaSeconds)
      if (Object.keys(patch).length > 0) {
        updateClipDuringGesture(trackIndex, clipIndex, patch)
      }
    }
    function onUp() {
      if (dragRef.current) endGesture()
      dragRef.current = null
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
  }, [track.type, trackIndex, clipIndex, updateClipDuringGesture, endGesture])

  /** Select a clip and also seek the video to the start of that clip, to see right away which segment is being edited. */
  function selectAndSeek() {
    select({ trackIndex, clipIndex })
    requestSeek(start)
  }

  function handlePointerDown(e: React.PointerEvent<HTMLElement>) {
    e.stopPropagation()
    const mode = (e.currentTarget.dataset.dragMode as DragMode | undefined) ?? 'move'
    selectAndSeek()
    dragRef.current = { mode, startX: e.clientX, original: clip }
    beginGesture()
  }

  // A logo shown for the whole video (no start/end) cannot be dragged: dragging would create a
  // time range the user never asked for.
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
  /** Waveform of the FIRST audio track (usually the narration) — simplified for the
   * MVP, no separate waveform computed yet for each different audio track/clip. */
  waveformPeaks?: number[]
  /** Second currently playing in the preview — draws the playhead line. */
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

  /** Click on the time ruler to seek there. */
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

  // Time tick marks: sparser as you zoom out so the text is not crowded.
  const tickStep = pxPerSecond >= 80 ? 1 : pxPerSecond >= 30 ? 5 : pxPerSecond >= 12 ? 15 : 60
  const ticks = Array.from(
    { length: Math.floor(totalDuration / tickStep) + 1 },
    (_, i) => i * tickStep
  )

  return (
    <div className='overflow-x-auto rounded-md border' onPointerDown={() => clearSelection()}>
      <div className='relative' style={{ width: timelineWidth, minWidth: '100%' }}>
        {/* Time ruler — click to seek. */}
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

        {/* The playhead covers all tracks, ignoring the mouse so it does not block dragging clips. */}
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
