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

/** Biến thể file nào có sẵn để xem trước — ưu tiên bản đã xử lý nhiều nhất. */
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

/** Tách riêng + bọc `memo`: gõ chữ ở 1 câu trước đây chạy lại hàm render của
 * TOÀN BỘ danh sách (vì `.map` nội tuyến trong component cha) — giờ chỉ hàng
 * đang gõ render lại, các hàng khác giữ nguyên vì props không đổi. */
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
 * Bọc ngoài để reset bản nháp bằng `key` thay vì dùng effect đồng bộ state —
 * mỗi lần mở lại (hoặc phụ đề đổi vì vừa dịch xong) là một instance mới.
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

  // Danh sách vai đã có (từ bước "Phân vai người nói") để đổ vào dropdown sửa
  // tay — chỉ hiện khi ít nhất 1 đoạn đã có speaker, không ép mọi video phải
  // phân vai mới sửa được phụ đề.
  const knownSpeakers = useMemo(() => {
    const set = new Set(segments.map((s) => s.speaker).filter(Boolean))
    return Array.from(set).sort()
  }, [segments])

  // Câu đang phát — dùng để tô sáng.
  const activeIndex = useMemo(
    () => draft.findIndex((s) => currentTime >= s.start && currentTime < s.end),
    [draft, currentTime]
  )

  // Ảo hoá danh sách: video dài (faster-whisper ra ~1 segment/vài giây) có thể
  // ra 500-1000+ câu — dựng hết cả list = 500-1000+ Textarea DOM node cùng lúc.
  // `measureElement` đo chiều cao thật từng hàng (không cố định, tuỳ nội dung).
  const rowVirtualizer = useVirtualizer({
    count: draft.length,
    getScrollElement: () => listScrollRef.current,
    estimateSize: () => 130,
    overscan: 8,
  })

  // Bẫy đã tự đo được: `ResizeObserver` của virtualizer không nhận đúng kích
  // thước container ở lần đo ĐẦU TIÊN khi nằm trong Radix Dialog (dialog vẫn
  // đang định vị/animate lúc đó) — danh sách ra rỗng dù container đã có kích
  // thước thật. Ép 1 lần re-render ngay sau mount để virtualizer đo lại đúng.
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

  // useCallback: giữ nguyên identity giữa các lần render để `SegmentRow`
  // (bọc `memo`) không bị buộc render lại chỉ vì cha render lại — nếu không,
  // gõ 1 ký tự ở câu này vẫn kéo theo tính lại hàm render của MỌI câu khác.
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

            {/* Phụ đề của câu đang phát, hiện to để đọc được khi xem. */}
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
