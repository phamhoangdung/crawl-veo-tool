import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Play, RotateCcw, Save } from 'lucide-react'
import { toast } from 'sonner'
import {
  API_BASE_URL,
  updateTranscript,
  type TranscriptSegment,
} from '@/lib/api'
import { formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'

/** Which file variants are available for preview — prefer the most processed version. */
function pickVariant(available: { burned: boolean; dubbed: boolean; original: boolean }) {
  if (available.burned) return 'burned'
  if (available.dubbed) return 'dubbed'
  if (available.original) return 'original'
  return null
}

type EditorProps = {
  videoId: number
  title: string
  segments: TranscriptSegment[]
  availableVariants: { burned: boolean; dubbed: boolean; original: boolean }
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Split out + wrapped in `memo`: typing in 1 sentence used to re-run the render function of
 * THE WHOLE list (because of the inline `.map` in the parent component) — now only the row
 * being typed in re-renders, the other rows stay as they are because their props do not change. */
const SegmentRow = memo(function SegmentRow({
  segment,
  index,
  isActive,
  knownSpeakers,
  onSeek,
  onUpdate,
}: {
  segment: TranscriptSegment
  index: number
  isActive: boolean
  knownSpeakers: string[]
  onSeek: (seconds: number) => void
  onUpdate: (index: number, patch: Partial<TranscriptSegment>) => void
}) {
  return (
    <div
      className={cn(
        'space-y-1.5 rounded-lg border p-2',
        isActive && 'border-primary bg-primary/5'
      )}
    >
      <button
        type='button'
        onClick={() => onSeek(segment.start)}
        className='flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground'
        title='Nhảy tới câu này'
      >
        <Play className='size-3' />
        {formatTime(segment.start)} → {formatTime(segment.end)}
      </button>

      <Textarea
        value={segment.text}
        onChange={(e) => onUpdate(index, { text: e.target.value })}
        rows={1}
        className='min-h-0 resize-none text-xs'
        placeholder='Lời thoại gốc'
      />
      <Textarea
        value={segment.translated_text}
        onChange={(e) => onUpdate(index, { translated_text: e.target.value })}
        rows={1}
        className='min-h-0 resize-none text-xs text-primary'
        placeholder='Bản dịch tiếng Việt'
      />
      {knownSpeakers.length > 0 && (
        <select
          value={segment.speaker}
          onChange={(e) => onUpdate(index, { speaker: e.target.value })}
          className='h-6 rounded-md border bg-transparent px-1.5 text-[11px]'
          title='Vai người nói — sửa tay nếu nhận nhầm'
        >
          <option value=''>(chưa xác định)</option>
          {knownSpeakers.map((speaker) => (
            <option key={speaker} value={speaker}>
              {speaker}
            </option>
          ))}
        </select>
      )}
    </div>
  )
})

/**
 * Outer wrapper to reset the draft via `key` instead of using an effect to sync state —
 * every time it reopens (or the subtitles change because a translation just finished) it is a new instance.
 */
export function SubtitleEditor(props: EditorProps) {
  if (!props.open) return null
  return <SubtitleEditorContent key={props.segments.length} {...props} />
}

function SubtitleEditorContent({
  videoId,
  title,
  segments,
  availableVariants,
  open,
  onOpenChange,
}: EditorProps) {
  const queryClient = useQueryClient()
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const listScrollRef = useRef<HTMLDivElement | null>(null)
  const [draft, setDraft] = useState<TranscriptSegment[]>(segments)
  const [currentTime, setCurrentTime] = useState(0)

  const variant = pickVariant(availableVariants)
  const videoUrl = variant
    ? `${API_BASE_URL}/api/library/${videoId}/stream?variant=${variant}`
    : null

  const isDirty = useMemo(
    () =>
      draft.some(
        (segment, i) =>
          segment.text !== segments[i]?.text ||
          segment.translated_text !== segments[i]?.translated_text ||
          segment.speaker !== segments[i]?.speaker
      ),
    [draft, segments]
  )

  // The list of speakers that exist (from the "Speaker separation" step) to fill the dropdown for hand
  // editing — only shown when at least 1 segment has a speaker, not forcing every video to
  // have speakers separated before its subtitles can be edited.
  const knownSpeakers = useMemo(() => {
    const set = new Set(segments.map((s) => s.speaker).filter(Boolean))
    return Array.from(set).sort()
  }, [segments])

  // The sentence being played — used for highlighting.
  const activeIndex = useMemo(
    () => draft.findIndex((s) => currentTime >= s.start && currentTime < s.end),
    [draft, currentTime]
  )

  // Virtualize the list: a long video (faster-whisper yields ~1 segment per few seconds) can
  // produce 500-1000+ sentences — building the whole list = 500-1000+ Textarea DOM nodes at once.
  // `measureElement` measures the real height of each row (not fixed, depending on content).
  const rowVirtualizer = useVirtualizer({
    count: draft.length,
    getScrollElement: () => listScrollRef.current,
    estimateSize: () => 130,
    overscan: 8,
  })

  // A trap found by measuring: the virtualizer's `ResizeObserver` does not get the right container
  // size on the FIRST measurement when inside a Radix Dialog (the dialog is still
  // positioning/animating at that time) — the list comes out empty even though the container already has a
  // real size. Force 1 re-render right after mount so the virtualizer measures again correctly.
  const [, forceRemeasure] = useState(0)
  useEffect(() => {
    forceRemeasure((n) => n + 1)
  }, [])

  const save = useMutation({
    mutationFn: () => updateTranscript(videoId, draft),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['video', videoId] })
      toast.success('Đã lưu phụ đề.')
    },
    onError: () => toast.error('Không lưu được phụ đề.'),
  })

  // useCallback: keep the identity stable between renders so `SegmentRow`
  // (wrapped in `memo`) is not forced to re-render just because the parent re-renders — otherwise,
  // typing 1 character in this sentence would still trigger recomputing the render function of EVERY other sentence.
  const updateSegment = useCallback((index: number, patch: Partial<TranscriptSegment>) => {
    setDraft((prev) =>
      prev.map((segment, i) => (i === index ? { ...segment, ...patch } : segment))
    )
  }, [])

  const seekTo = useCallback((seconds: number) => {
    const video = videoRef.current
    if (!video) return
    video.currentTime = seconds
    void video.play()
  }, [])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='flex max-h-[90vh] w-full max-w-5xl flex-col gap-0 p-0'>
        <DialogHeader className='border-b p-4'>
          <DialogTitle className='line-clamp-1 text-start'>{title}</DialogTitle>
          <DialogDescription className='text-start'>
            Xem trước và sửa phụ đề. Bấm vào mốc thời gian để nhảy tới câu đó.
          </DialogDescription>
        </DialogHeader>

        <div className='grid min-h-0 flex-1 lg:grid-cols-2'>
          <div className='space-y-3 border-b p-4 lg:border-e lg:border-b-0'>
            {videoUrl ? (
              <>
                <video
                  ref={videoRef}
                  src={videoUrl}
                  controls
                  className='max-h-[50vh] w-full rounded-lg bg-black object-contain'
                  onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                />
                <p className='text-xs text-muted-foreground'>
                  Đang xem bản:{' '}
                  {variant === 'burned'
                    ? 'có phụ đề cứng'
                    : variant === 'dubbed'
                      ? 'đã lồng tiếng'
                      : 'gốc'}
                </p>
              </>
            ) : (
              <p className='text-sm text-muted-foreground'>
                Chưa có file video để xem trước. Tải video về trước đã.
              </p>
            )}

            {/* The subtitle of the sentence being played, shown large to be readable while watching. */}
            <div className='min-h-20 rounded-lg border bg-muted/40 p-3'>
              {activeIndex >= 0 ? (
                <>
                  <p className='text-sm'>{draft[activeIndex].text}</p>
                  <p className='mt-1 text-sm font-medium text-primary'>
                    {draft[activeIndex].translated_text || '(chưa dịch)'}
                  </p>
                </>
              ) : (
                <p className='text-sm text-muted-foreground'>
                  Phụ đề sẽ hiện ở đây khi video chạy tới câu có lời.
                </p>
              )}
            </div>
          </div>

          <div className='flex min-h-0 flex-col'>
            <div className='flex items-center gap-2 border-b px-4 py-2'>
              <p className='flex-1 text-sm font-medium'>{draft.length} câu</p>
              {isDirty && (
                <Button
                  size='sm'
                  variant='ghost'
                  className='h-7 gap-1 text-xs'
                  onClick={() => setDraft(segments)}
                >
                  <RotateCcw className='size-3' />
                  Hoàn tác
                </Button>
              )}
              <Button
                size='sm'
                className='h-7 gap-1 text-xs'
                disabled={!isDirty || save.isPending}
                onClick={() => save.mutate()}
              >
                <Save className='size-3' />
                {save.isPending ? 'Đang lưu...' : 'Lưu'}
              </Button>
            </div>

            <div ref={listScrollRef} className='min-h-0 flex-1 overflow-y-auto p-3'>
              <div
                role='list'
                style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}
              >
                {rowVirtualizer.getVirtualItems().map((virtualRow) => (
                  <div
                    key={virtualRow.key}
                    data-index={virtualRow.index}
                    ref={rowVirtualizer.measureElement}
                    role='listitem'
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      transform: `translateY(${virtualRow.start}px)`,
                      paddingBottom: 8,
                    }}
                  >
                    <SegmentRow
                      segment={draft[virtualRow.index]}
                      index={virtualRow.index}
                      isActive={virtualRow.index === activeIndex}
                      knownSpeakers={knownSpeakers}
                      onSeek={seekTo}
                      onUpdate={updateSegment}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
