import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { toast } from 'sonner'
import {
  createCrawlJob,
  downloadVideo,
  loadMoreJobVideos,
  type JobWithVideosRead,
  type VideoRead,
} from '@/lib/api'
import { useInfiniteScroll } from '@/hooks/use-infinite-scroll'
import { CoverImage } from '@/components/cover-image'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { TaskMonitor } from '@/components/task-monitor'
import { ThemeSwitch } from '@/components/theme-switch'

function formatDuration(seconds: number | null) {
  if (seconds === null) return '—'
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes}:${rest.toString().padStart(2, '0')}`
}

// Trang Crawl chỉ lo tìm và tải; các bước xử lý (tách lời, dịch, lồng tiếng)
// nằm ở trang Quản lý file — nơi thấy được file thật.
const DOWNLOADABLE: string[] = ['queued', 'failed_download']

function VideoRow({
  video,
  onUpdate,
}: {
  video: VideoRead
  onUpdate: (id: number, patch: Partial<VideoRead>) => void
}) {
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => downloadVideo(video.id),
    onSuccess: (result) => {
      // Tải chạy nền: phản hồi chỉ xác nhận đã nhận việc, tiến độ xem ở dock.
      onUpdate(video.id, { status: result.status as VideoRead['status'] })
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Đã thêm vào hàng đợi tải. Xem tiến độ ở icon tác vụ trên thanh trên.')
    },
    onError: (error) =>
      toast.error(
        error instanceof Error && 'response' in error
          ? 'Video này đang được tải.'
          : 'Không bắt đầu tải được.'
      ),
  })

  const canDownload = DOWNLOADABLE.includes(video.status)
  const isFailed = video.status.startsWith('failed_')

  return (
    <TableRow>
      <TableCell>
        <CoverImage src={video.cover_url} className='w-24 rounded' />
      </TableCell>
      <TableCell>
        <a href={video.source_url} target='_blank' rel='noreferrer' className='hover:underline'>
          {video.title}
        </a>
      </TableCell>
      <TableCell>{video.author_name ?? '—'}</TableCell>
      <TableCell>{formatDuration(video.duration_seconds)}</TableCell>
      <TableCell>
        <Badge variant={isFailed ? 'destructive' : 'outline'}>{video.status}</Badge>
      </TableCell>
      <TableCell>
        {canDownload && (
          <Button size='sm' disabled={mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? 'Đang thêm...' : 'Tải video'}
          </Button>
        )}
        {video.status === 'downloading' && (
          <span className='text-xs text-muted-foreground'>Đang tải...</span>
        )}
        {!canDownload && video.status !== 'downloading' && (
          <Link to='/files' className='text-xs text-muted-foreground hover:underline'>
            Xử lý ở Quản lý file →
          </Link>
        )}
      </TableCell>
    </TableRow>
  )
}

export function Crawl() {
  const [keyword, setKeyword] = useState('')
  const [translateKeyword, setTranslateKeyword] = useState(true)
  const [job, setJob] = useState<JobWithVideosRead | null>(null)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)

  const mutation = useMutation({
    mutationFn: (kw: string) => createCrawlJob(kw, { translateKeyword }),
    onSuccess: (data) => {
      setJob(data)
      setPage(1)
      // Job vừa tạo luôn từ search nên gần như chắc chắn còn trang sau.
      setHasMore(data.videos.length > 0)
      if (data.translation_failed) {
        toast.warning(
          `Dịch từ khoá thất bại, đã tìm bằng nguyên văn "${data.keyword}" (dễ ra ít/không có kết quả). Kiểm tra lại API key dịch trong Cài đặt.`
        )
      }
    },
  })

  const loadMore = useMutation({
    mutationFn: () => {
      if (!job) throw new Error('Chưa có job')
      return loadMoreJobVideos(job.id, page + 1)
    },
    onSuccess: (result) => {
      setPage(result.page)
      setHasMore(result.has_more)
      setJob((prev) =>
        prev ? { ...prev, videos: [...prev.videos, ...result.videos] } : prev
      )
    },
    onError: () => {
      setHasMore(false)
      toast.error('Không tải thêm được video.')
    },
  })

  const sentinelRef = useInfiniteScroll({
    enabled: hasMore && !loadMore.isPending && !mutation.isPending,
    onReachEnd: () => loadMore.mutate(),
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
          <h1 className='text-2xl font-bold tracking-tight'>Crawl</h1>
          <p className='text-muted-foreground'>
            Nhập từ khoá để tìm và tải video từ Bilibili.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Tạo job crawl</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className='space-y-3'
              onSubmit={(e) => {
                e.preventDefault()
                if (keyword.trim()) mutation.mutate(keyword.trim())
              }}
            >
              <div className='flex gap-2'>
                <Input
                  placeholder='Nhập từ khoá, vd: ẩm thực'
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  disabled={mutation.isPending}
                />
                <Button type='submit' disabled={mutation.isPending || !keyword.trim()}>
                  {mutation.isPending ? 'Đang tìm...' : 'Crawl'}
                </Button>
              </div>
              <label className='flex items-center gap-2 text-sm text-muted-foreground'>
                <Checkbox
                  checked={translateKeyword}
                  onCheckedChange={(checked) => setTranslateKeyword(checked === true)}
                  disabled={mutation.isPending}
                />
                Dịch từ khoá sang tiếng Trung giản thể trước khi tìm
              </label>
            </form>
            {mutation.isError && (
              <p className='mt-2 text-sm text-destructive'>
                Có lỗi khi crawl: {(mutation.error as Error).message}
              </p>
            )}
          </CardContent>
        </Card>

        {job && (
          <Card className='mt-4'>
            <CardHeader>
              <CardTitle>
                Kết quả cho &quot;{job.keyword}&quot; ({job.videos.length} video)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className='w-28'>Ảnh</TableHead>
                    <TableHead>Tiêu đề</TableHead>
                    <TableHead>Tác giả</TableHead>
                    <TableHead>Thời lượng</TableHead>
                    <TableHead>Trạng thái</TableHead>
                    <TableHead>Thao tác</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {job.videos.map((video) => (
                    <VideoRow
                      key={video.id}
                      video={video}
                      onUpdate={(id, patch) =>
                        setJob((prev) =>
                          prev
                            ? {
                                ...prev,
                                videos: prev.videos.map((v) =>
                                  v.id === id ? { ...v, ...patch } : v
                                ),
                              }
                            : prev
                        )
                      }
                    />
                  ))}
                </TableBody>
              </Table>

              {/* Sentinel: lọt vào tầm nhìn thì tải thêm trang kết quả. */}
              <div ref={sentinelRef} className='h-px' />

              {loadMore.isPending && (
                <p className='py-3 text-center text-sm text-muted-foreground'>
                  Đang tải thêm...
                </p>
              )}
              {!hasMore && job.videos.length > 0 && (
                <p className='py-3 text-center text-sm text-muted-foreground'>
                  Đã hết kết quả cho từ khoá này.
                </p>
              )}
            </CardContent>
          </Card>
        )}
      </Main>
    </>
  )
}
