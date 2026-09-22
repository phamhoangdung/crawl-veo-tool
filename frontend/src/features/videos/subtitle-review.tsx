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

/** Tách riêng + bọc `memo`: `activeIndex` đổi mỗi lần video phát tiếp (nhiều
 * lần/giây qua `onTimeUpdate`) — không tách thì MỌI hàng render lại theo, dù
 * chỉ 1 hàng thật sự đổi trạng thái tô sáng. */
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
 * Soát phụ đề theo ngữ cảnh: video chạy bên trái, danh sách câu bên phải tự cuộn
 * và tô sáng câu đang phát. Chỉ để ĐỌC — sửa thì mở SubtitleEditor.
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

  // Ảo hoá: video dài ra hàng trăm câu, dựng hết cả list = hàng trăm node
  // cùng lúc dù chỉ vài chục cái lọt trong khung nhìn thấy.
  const rowVirtualizer = useVirtualizer({
    count: segments.length,
    getScrollElement: () => listRef.current,
    estimateSize: () => 52,
    overscan: 8,
  })

  // `ResizeObserver` của virtualizer có thể đo ra 0 hàng ở lần đo đầu tiên nếu
  // container chưa kịp có kích thước cuối cùng lúc đó (xem SubtitleEditor —
  // cùng bẫy, xảy ra rõ nhất với danh sách dài). Ép 1 lần re-render ngay sau
  // mount để virtualizer đo lại đúng.
  const [, forceRemeasure] = useState(0)
  useEffect(() => {
    forceRemeasure((n) => n + 1)
  }, [])

  // Cuộn câu đang phát vào giữa khung. Tắt được vì người dùng có thể muốn đọc
  // chỗ khác trong lúc video vẫn chạy. Dùng `scrollToIndex` của virtualizer
  // (không phải `list.children[activeIndex]`) vì khi ảo hoá, con thật sự trong
  // DOM không còn khớp 1-1 với index của mảng segments nữa.
  useEffect(() => {
    if (!autoScroll || activeIndex < 0) return
    rowVirtualizer.scrollToIndex(activeIndex, { align: 'center', behavior: 'smooth' })
  }, [activeIndex, autoScroll, rowVirtualizer])

  // useCallback: giữ identity ổn định để `SegmentButton` (bọc `memo`) không bị
  // buộc render lại mỗi khi cha render lại vì 1 prop hàm mới mỗi lần.
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
          {/* Khoá theo CHIỀU CAO chứ không chỉ bề rộng: video dọc 9:16 mà chỉ đặt
              w-full thì cao gấp ~1.8 lần bề rộng cột, đẩy phần còn lại ra ngoài
              màn hình. object-contain giữ nguyên tỉ lệ gốc — video dọc và ngang
              dùng chung khung này, chỉ khác phần nền đen hai bên. */}
          <video
            ref={videoRef}
            src={`${API_BASE_URL}/api/library/${videoId}/stream?variant=${variant}`}
            controls
            className='max-h-[min(60vh,32rem)] w-full rounded-lg bg-black object-contain'
            onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
          />

          {/* Câu đang phát, hiện to để đọc được khi mắt đang nhìn video. */}
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
