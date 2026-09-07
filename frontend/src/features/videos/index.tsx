import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { ChevronRight, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  cleanupOrphanFiles,
  deleteVideoFiles,
  getStorageSummary,
  getVideoFiles,
  type VideoFiles,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { useTaskProgress } from '@/hooks/use-task-progress'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfigDrawer } from '@/components/config-drawer'
import { CoverImage } from '@/components/cover-image'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { TaskMonitor } from '@/components/task-monitor'
import { ThemeSwitch } from '@/components/theme-switch'

function formatBytes(bytes: number) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

/** Nhãn tiếng Việt cho trạng thái — tên enum của backend không dành cho người đọc. */
const STATUS_LABELS: Record<string, string> = {
  queued: 'Chờ tải',
  downloading: 'Đang tải',
  downloaded: 'Đã tải',
  separating_audio: 'Đang tách nhạc nền',
  transcribing: 'Đang tách lời',
  transcribed: 'Đã tách lời',
  translating: 'Đang dịch',
  translated: 'Đã dịch',
  dubbing: 'Đang lồng tiếng',
  muxing: 'Đang ghép',
  done: 'Hoàn tất',
  paused_quota: 'Tạm dừng (hết quota AI, thử lại sau)',
  failed_download: 'Lỗi tải',
  failed_separating_audio: 'Lỗi tách nhạc nền',
  failed_transcribing: 'Lỗi tách lời',
  failed_translating: 'Lỗi dịch',
  failed_dubbing: 'Lỗi lồng tiếng',
  failed_muxing: 'Lỗi ghép',
}

function VideoCard({ item }: { item: VideoFiles }) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)

  // Tác vụ đang chạy trên video này — danh sách chỉ cần biết "đang làm gì".
  // Dữ liệu do TaskMonitor đẩy vào cache qua SSE, không tự gọi API.
  const tasks = useTaskProgress()
  const activeTasks = tasks.filter(
    (t) => t.video_id === item.video_id && t.is_running
  )

  const removeAll = useMutation({
    mutationFn: () => deleteVideoFiles(item.video_id),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['files'] })
      setConfirming(false)
      toast.success(`Đã giải phóng ${formatBytes(result.freed_bytes)}.`)
    },
    onError: () => toast.error('Không xoá được thư mục.'),
  })

  const isFailed = item.status.startsWith('failed_')

  return (
    <Card className='gap-0 overflow-hidden py-0'>
      <div className='flex'>
        <Link
          to='/videos/$videoId'
          params={{ videoId: String(item.video_id) }}
          className='group relative shrink-0'
          title='Mở chi tiết'
        >
          <CoverImage src={item.cover_url} className='h-full w-36 sm:w-44' />
          <span className='absolute inset-0 flex items-center justify-center bg-black/0 transition-colors group-hover:bg-black/30'>
            <ChevronRight className='size-6 text-white opacity-0 transition-opacity group-hover:opacity-100' />
          </span>
        </Link>

        <div className='flex min-w-0 flex-1 flex-col justify-between gap-2 p-3'>
          <div className='space-y-1'>
            <Link
              to='/videos/$videoId'
              params={{ videoId: String(item.video_id) }}
              className='block text-sm font-medium hover:underline'
            >
              <span className='line-clamp-2'>{item.title}</span>
            </Link>
            <div className='flex flex-wrap items-center gap-2 text-xs text-muted-foreground'>
              <Badge
                variant={isFailed ? 'destructive' : 'outline'}
                className={cn(
                  'text-[11px]',
                  item.status === 'done' && 'border-green-500 text-green-600'
                )}
              >
                {STATUS_LABELS[item.status] ?? item.status}
              </Badge>
              <span>{formatBytes(item.total_bytes)}</span>
              <span>{item.files.length} file</span>
            </div>
          </div>

          {activeTasks.length > 0 && (
            <div className='space-y-1'>
              {activeTasks.map((task) => (
                <div key={task.kind} className='space-y-0.5'>
                  <p className='text-[11px] text-muted-foreground'>
                    {task.kind_label}
                    {task.total ? ` · ${task.percent}%` : ` · ${task.stage_label}`}
                  </p>
                  <div className='h-1 overflow-hidden rounded-full bg-muted'>
                    <div
                      className={cn(
                        'h-full rounded-full bg-primary',
                        task.total ? 'transition-[width] duration-300' : 'animate-pulse'
                      )}
                      style={{ width: task.total ? `${task.percent}%` : '100%' }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className='flex items-center gap-2'>
            <Button asChild size='sm' variant='outline' className='h-7 text-xs'>
              <Link to='/videos/$videoId' params={{ videoId: String(item.video_id) }}>
                Chi tiết & xử lý
              </Link>
            </Button>
            {confirming ? (
              <span className='ms-auto flex items-center gap-1.5'>
                <Button
                  size='sm'
                  variant='destructive'
                  className='h-7 text-xs'
                  disabled={removeAll.isPending}
                  onClick={() => removeAll.mutate()}
                >
                  Xoá
                </Button>
                <Button
                  size='sm'
                  variant='ghost'
                  className='h-7 text-xs'
                  onClick={() => setConfirming(false)}
                >
                  Huỷ
                </Button>
              </span>
            ) : (
              <Button
                size='icon'
                variant='ghost'
                className='ms-auto size-7 text-muted-foreground hover:text-destructive'
                title='Xoá toàn bộ file của video'
                onClick={() => setConfirming(true)}
              >
                <Trash2 className='size-3.5' />
              </Button>
            )}
          </div>
        </div>
      </div>
    </Card>
  )
}

export function Videos() {
  const queryClient = useQueryClient()

  const { data: items, isLoading } = useQuery({
    queryKey: ['files'],
    queryFn: getVideoFiles,
  })

  const { data: summary } = useQuery({
    queryKey: ['files', 'summary'],
    queryFn: getStorageSummary,
  })

  const cleanup = useMutation({
    mutationFn: cleanupOrphanFiles,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['files'] })
      toast.success(
        result.freed_bytes > 0
          ? `Đã giải phóng ${formatBytes(result.freed_bytes)}.`
          : 'Không có file rác nào để dọn.'
      )
    },
    onError: () => toast.error('Không dọn được file rác.'),
  })

  return (
    <>
      <Header>
        <Search />
        <div className='ms-auto flex items-center space-x-4'>
          <TaskMonitor />
          <ThemeSwitch />
          <ConfigDrawer />
          <ProfileDropdown />
        </div>
      </Header>

      <Main>
        <div className='mb-4'>
          <h1 className='text-2xl font-bold tracking-tight'>Video của tôi</h1>
          <p className='text-muted-foreground'>
            Video đã tải về máy. Bấm vào từng video để tách lời, dịch và lồng tiếng.
          </p>
        </div>

        {summary && (
          <Card className='mb-6'>
            <CardHeader>
              <CardTitle className='text-base'>Dung lượng</CardTitle>
              <CardDescription>
                <code className='rounded bg-muted px-1.5 py-0.5 text-xs'>
                  {summary.storage_root}
                </code>
              </CardDescription>
            </CardHeader>
            <CardContent className='flex flex-wrap items-center gap-6'>
              <div>
                <p className='text-2xl font-semibold'>{formatBytes(summary.total_bytes)}</p>
                <p className='text-xs text-muted-foreground'>
                  {summary.video_count} video đã tải
                </p>
              </div>
              {summary.orphan_bytes > 0 && (
                <div>
                  <p className='text-2xl font-semibold text-amber-600'>
                    {formatBytes(summary.orphan_bytes)}
                  </p>
                  <p className='text-xs text-muted-foreground'>File rác không dùng tới</p>
                </div>
              )}
              <Button
                size='sm'
                variant='outline'
                className='ms-auto'
                disabled={cleanup.isPending}
                onClick={() => cleanup.mutate()}
              >
                {cleanup.isPending ? 'Đang dọn...' : 'Dọn file rác'}
              </Button>
            </CardContent>
          </Card>
        )}

        {isLoading && (
          <div className='grid gap-4 lg:grid-cols-2'>
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className='h-32 w-full rounded-xl' />
            ))}
          </div>
        )}

        {items && items.length === 0 && (
          <p className='text-muted-foreground'>
            Chưa có video nào. Sang trang Crawl hoặc Trending để tải về.
          </p>
        )}

        <div className='grid gap-4 lg:grid-cols-2'>
          {items?.map((item) => (
            <VideoCard key={item.video_id} item={item} />
          ))}
        </div>
      </Main>
    </>
  )
}
