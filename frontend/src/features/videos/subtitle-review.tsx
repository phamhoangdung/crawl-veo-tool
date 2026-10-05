import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Pencil, Play } from 'lucide-react'
import { API_BASE_URL, type TranscriptSegment } from '@/lib/api'
import { formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

/** Split out + wrapped in `memo`: `activeIndex` changes every time the video plays on (many
 * times per second via `onTimeUpdate`) — if not split, EVERY row re-renders along, even though
 * only 1 row really changed its highlight state. */
const SegmentButton = memo(function SegmentButton({
  segment,
  isActive,
  onSeek,
}: {
  segment: TranscriptSegment
  isActive: boolean
  onSeek: (seconds: number) => void
}) {
  return (
    <button
      type='button'
      onClick={() => onSeek(segment.start)}
      className={cn(
        'flex w-full gap-2 rounded border px-2 py-1.5 text-start text-sm transition-colors hover:bg-accent',
        isActive && 'border-primary bg-primary/5'
      )}
    >
      <span className='flex w-12 shrink-0 items-center gap-1 text-xs text-muted-foreground tabular-nums'>
        <Play className='size-2.5' />
        {formatTime(segment.start)}
      </span>
      <span className='min-w-0'>
        <span className='block'>{segment.text}</span>
        {segment.translated_text && (
          <span className='block text-primary'>{segment.translated_text}</span>
        )}
      </span>
    </button>
  )
})

/**
 * Review subtitles in context: the video plays on the left, the sentence list on the right auto-scrolls
 * and highlights the sentence being played. READ-only — to edit, open SubtitleEditor.
 */
export function SubtitleReview({
  videoId,
  segments,
  hasTranslation,
  variant,
  onEdit,
}: {
  videoId: number
  segments: TranscriptSegment[]
  hasTranslation: boolean
  variant: 'original' | 'dubbed' | 'burned'
  onEdit: () => void
}) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [autoScroll, setAutoScroll] = useState(true)

  const activeIndex = useMemo(
    () => segments.findIndex((s) => currentTime >= s.start && currentTime < s.end),
    [segments, currentTime]
  )

  // Virtualization: a long video has hundreds of sentences, building the whole list = hundreds of nodes
  // at once even though only a few dozen fall within the visible frame.
  const rowVirtualizer = useVirtualizer({
    count: segments.length,
    getScrollElement: () => listRef.current,
    estimateSize: () => 52,
    overscan: 8,
  })

  // The virtualizer's `ResizeObserver` may measure 0 rows on the first measurement if the
  // container does not yet have its final size at that moment (see SubtitleEditor —
  // the same trap, most visible with long lists). Force 1 re-render right after
  // mount so the virtualizer measures again correctly.
  const [, forceRemeasure] = useState(0)
  useEffect(() => {
    forceRemeasure((n) => n + 1)
  }, [])

  // Scroll the sentence being played into the middle of the frame. Can be turned off because the user may want to read
  // elsewhere while the video keeps playing. Uses the virtualizer's `scrollToIndex`
  // (not `list.children[activeIndex]`) because with virtualization, the children actually in the
  // DOM no longer match 1-to-1 with the index of the segments array.
  useEffect(() => {
    if (!autoScroll || activeIndex < 0) return
    rowVirtualizer.scrollToIndex(activeIndex, { align: 'center', behavior: 'smooth' })
  }, [activeIndex, autoScroll, rowVirtualizer])

  // useCallback: keep a stable identity so `SegmentButton` (wrapped in `memo`) is not
  // forced to re-render every time the parent re-renders because of a new function prop each time.
  const seekTo = useCallback((seconds: number) => {
    const video = videoRef.current
    if (!video) return
    video.currentTime = seconds
    void video.play()
  }, [])

  return (
    <Card>
      <CardHeader>
        <div className='flex flex-wrap items-start justify-between gap-3'>
          <div>
            <CardTitle className='text-base'>Phụ đề ({segments.length} câu)</CardTitle>
            <CardDescription>
              {hasTranslation
                ? 'Bấm vào câu để nhảy tới đoạn đó trong video.'
                : 'Chưa dịch sang tiếng Việt.'}
            </CardDescription>
          </div>
          <Button size='sm' variant='outline' className='gap-1' onClick={onEdit}>
            <Pencil className='size-3.5' />
            Sửa phụ đề
          </Button>
        </div>
      </CardHeader>

      <CardContent className='grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] lg:items-start'>
        <div className='flex flex-col gap-3'>
          {/* Lock by HEIGHT, not just width: a vertical 9:16 video with only
              w-full is ~1.8 times taller than the column width, pushing the rest off the
              screen. object-contain keeps the original ratio — vertical and landscape videos
              share this frame, differing only in the black background on the two sides. */}
          <video
            ref={videoRef}
            src={`${API_BASE_URL}/api/library/${videoId}/stream?variant=${variant}`}
            controls
            className='max-h-[min(60vh,32rem)] w-full rounded-lg bg-black object-contain'
            onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
          />

          {/* The sentence being played, shown large to be readable while the eyes are on the video. */}
          <div className='min-h-20 rounded-lg border bg-muted/40 p-3'>
            {activeIndex >= 0 ? (
              <>
                <p className='text-sm'>{segments[activeIndex].text}</p>
                <p className='mt-1 text-sm font-medium text-primary'>
                  {segments[activeIndex].translated_text || '(chưa dịch)'}
                </p>
              </>
            ) : (
              <p className='text-sm text-muted-foreground'>
                Phụ đề hiện ở đây khi video chạy tới câu có lời.
              </p>
            )}
          </div>

          <label className='flex items-center gap-2 text-xs text-muted-foreground'>
            <input
              type='checkbox'
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className='accent-primary'
            />
            Tự cuộn theo video
          </label>
        </div>

        <ul ref={listRef} className='h-[min(70vh,40rem)] overflow-y-auto pe-1'>
          <div style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}>
            {rowVirtualizer.getVirtualItems().map((virtualRow) => (
              <li
                key={virtualRow.key}
                data-index={virtualRow.index}
                ref={rowVirtualizer.measureElement}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  transform: `translateY(${virtualRow.start}px)`,
                  paddingBottom: 6,
                }}
              >
                <SegmentButton
                  segment={segments[virtualRow.index]}
                  isActive={virtualRow.index === activeIndex}
                  onSeek={seekTo}
                />
              </li>
            ))}
          </div>
        </ul>
      </CardContent>
    </Card>
  )
}
