import { useEffect, useMemo, useRef, useState } from 'react'
import { Pencil, Play } from 'lucide-react'
import { API_BASE_URL, type TranscriptSegment } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

function formatTime(seconds: number) {
  const total = Math.max(0, Math.floor(seconds))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

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

  // Cuộn câu đang phát vào giữa khung. Tắt được vì người dùng có thể muốn đọc
  // chỗ khác trong lúc video vẫn chạy.
  useEffect(() => {
    if (!autoScroll || activeIndex < 0) return
    const list = listRef.current
    const item = list?.children[activeIndex] as HTMLElement | undefined
    item?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [activeIndex, autoScroll])

  function seekTo(seconds: number) {
    const video = videoRef.current
    if (!video) return
    video.currentTime = seconds
    void video.play()
  }

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

      <CardContent className='grid gap-4 lg:grid-cols-2'>
        <div className='space-y-3'>
          <video
            ref={videoRef}
            src={`${API_BASE_URL}/api/library/${videoId}/stream?variant=${variant}`}
            controls
            className='w-full rounded-lg bg-black'
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

        <ul ref={listRef} className='max-h-[28rem] space-y-1.5 overflow-y-auto pe-1'>
          {segments.map((segment, index) => (
            <li key={index}>
              <button
                type='button'
                onClick={() => seekTo(segment.start)}
                className={cn(
                  'flex w-full gap-2 rounded border px-2 py-1.5 text-start text-sm transition-colors hover:bg-accent',
                  index === activeIndex && 'border-primary bg-primary/5'
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
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
