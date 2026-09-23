import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { CheckCircle2, FileVideo, Upload, XCircle } from 'lucide-react'
import { toast } from 'sonner'
import { getApiErrorMessage, importLocalVideo } from '@/lib/api'
import { formatBytes } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

const ACCEPT = '.mp4,.mkv,.mov,.avi,.webm,.flv,.m4v,.ts,.wmv,video/*'
const VIDEO_EXT = /\.(mp4|mkv|mov|avi|webm|flv|m4v|ts|wmv)$/i

type Item = {
  key: number
  name: string
  size: number
  percent: number
  state: 'uploading' | 'done' | 'error'
  videoId?: number
  error?: string
}

let nextKey = 1

/** Nhập video đã có sẵn trên máy (kéo thả hoặc chọn file) để đi tiếp pipeline
 * tách lời → dịch → lồng tiếng như video tải từ nền tảng. */
export function ImportPanel({ className }: { className?: string }) {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [items, setItems] = useState<Item[]>([])
  const [dragging, setDragging] = useState(false)
  const busy = useRef(false)
  const queue = useRef<{ key: number; file: File }[]>([])

  const patch = (key: number, change: Partial<Item>) =>
    setItems((prev) =>
      prev.map((i) => (i.key === key ? { ...i, ...change } : i))
    )

  async function drainQueue() {
    if (busy.current) return
    busy.current = true
    try {
      let entry = queue.current.shift()
      while (entry) {
        const { key, file } = entry
        try {
          const video = await importLocalVideo(file, (percent) =>
            patch(key, { percent })
          )
          patch(key, { state: 'done', percent: 100, videoId: video.id })
          queryClient.invalidateQueries({ queryKey: ['files'] })
        } catch (error) {
          patch(key, {
            state: 'error',
            error: getApiErrorMessage(error, 'Không nhập được file này.'),
          })
        }
        entry = queue.current.shift()
      }
    } finally {
      busy.current = false
    }
  }

  function enqueue(files: File[]) {
    const videos = files.filter(
      (f) => VIDEO_EXT.test(f.name) || f.type.startsWith('video/')
    )
    const skipped = files.length - videos.length
    if (skipped > 0) toast.error(`Bỏ qua ${skipped} file không phải video.`)
    if (videos.length === 0) return

    const entries = videos.map((file) => ({ key: nextKey++, file }))
    setItems((prev) => [
      ...entries.map(({ key, file }) => ({
        key,
        name: file.name,
        size: file.size,
        percent: 0,
        state: 'uploading' as const,
      })),
      ...prev,
    ])
    // Lần lượt từng file: hiện tiến độ riêng, không dồn nhiều request lớn cùng lúc.
    queue.current.push(...entries)
    void drainQueue()
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className='text-base'>Nhập video từ máy</CardTitle>
        <CardDescription>
          Đã có sẵn video? Đưa vào đây để dịch và lồng tiếng như video tải về.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div
          role='button'
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click()
          }}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            enqueue(Array.from(e.dataTransfer.files))
          }}
          className={cn(
            'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors',
            dragging
              ? 'border-primary bg-primary/5'
              : 'border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/40'
          )}
        >
          <Upload className='size-7 text-muted-foreground' />
          <p className='text-sm font-medium'>
            Kéo thả video vào đây hoặc bấm để chọn file
          </p>
          <p className='text-xs text-muted-foreground'>
            MP4, MKV, MOV, AVI, WEBM... — chọn được nhiều file cùng lúc
          </p>
          <input
            ref={inputRef}
            type='file'
            accept={ACCEPT}
            multiple
            className='hidden'
            data-testid='import-file-input'
            onChange={(e) => {
              enqueue(Array.from(e.target.files ?? []))
              e.target.value = ''
            }}
          />
        </div>

        {items.length > 0 && (
          <ul className='max-h-56 space-y-2 overflow-y-auto'>
            {items.map((item) => (
              <li key={item.key} className='rounded-md border p-2 text-sm'>
                <div className='flex items-center gap-2'>
                  {item.state === 'done' ? (
                    <CheckCircle2 className='size-4 shrink-0 text-green-600' />
                  ) : item.state === 'error' ? (
                    <XCircle className='size-4 shrink-0 text-destructive' />
                  ) : (
                    <FileVideo className='size-4 shrink-0 text-muted-foreground' />
                  )}
                  <span className='min-w-0 flex-1 truncate' title={item.name}>
                    {item.name}
                  </span>
                  <span className='shrink-0 text-xs text-muted-foreground tabular-nums'>
                    {formatBytes(item.size)}
                  </span>
                  {item.state === 'done' && item.videoId !== undefined && (
                    <Link
                      to='/videos/$videoId'
                      params={{ videoId: String(item.videoId) }}
                      className='shrink-0 text-xs text-primary underline'
                    >
                      Mở
                    </Link>
                  )}
                </div>
                {item.state === 'uploading' && (
                  <div className='mt-1.5 flex items-center gap-2'>
                    <div className='h-1.5 flex-1 overflow-hidden rounded-full bg-muted'>
                      <div
                        className='h-full rounded-full bg-primary transition-[width] duration-200'
                        style={{ width: `${item.percent}%` }}
                      />
                    </div>
                    <span className='w-9 text-end text-xs tabular-nums'>
                      {Math.round(item.percent)}%
                    </span>
                  </div>
                )}
                {item.state === 'error' && (
                  <p className='mt-1 text-xs text-destructive'>{item.error}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
