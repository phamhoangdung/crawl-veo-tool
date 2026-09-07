import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import {
  Captions,
  Clapperboard,
  Download,
  HardDrive,
  Languages,
  Mic,
  TrendingUp,
  TriangleAlert,
} from 'lucide-react'
import { getDashboardStats, getVideoFiles } from '@/lib/api'
import { APP_NAME } from '@/config/app'
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

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = 'default',
}: {
  label: string
  value: string
  hint?: string
  icon: typeof Download
  tone?: 'default' | 'warning'
}) {
  return (
    <Card>
      <CardHeader className='pb-2'>
        <div className='flex items-center justify-between'>
          <CardDescription>{label}</CardDescription>
          <Icon
            className={
              tone === 'warning' ? 'size-4 text-amber-600' : 'size-4 text-muted-foreground'
            }
          />
        </div>
      </CardHeader>
      <CardContent>
        <p className='text-2xl font-semibold'>{value}</p>
        {hint && <p className='text-xs text-muted-foreground'>{hint}</p>}
      </CardContent>
    </Card>
  )
}

export function Dashboard() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: getDashboardStats,
    // Số liệu đổi khi tác vụ chạy xong — làm mới định kỳ cho khỏi lệch.
    refetchInterval: 10_000,
  })

  const { data: videos } = useQuery({
    queryKey: ['files'],
    queryFn: getVideoFiles,
  })

  const recent = videos?.slice(0, 4) ?? []

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
        <div className='mb-6'>
          <h1 className='text-2xl font-bold tracking-tight'>{APP_NAME}</h1>
          <p className='text-muted-foreground'>
            Crawl video từ Bilibili, dịch và lồng tiếng Việt bằng AI.
          </p>
        </div>

        {isLoading ? (
          <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className='h-28 w-full rounded-xl' />
            ))}
          </div>
        ) : (
          stats && (
            <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
              <StatCard
                label='Video đã tải'
                value={String(stats.downloaded)}
                hint={`trong ${stats.total_videos} video đã tìm thấy`}
                icon={Download}
              />
              <StatCard
                label='Đã tách lời thoại'
                value={String(stats.transcribed)}
                hint={`${stats.translated} đã dịch sang tiếng Việt`}
                icon={Captions}
              />
              <StatCard
                label='Đã lồng tiếng'
                value={String(stats.dubbed)}
                hint={
                  stats.running_tasks > 0
                    ? `${stats.running_tasks} tác vụ đang chạy`
                    : 'Không có tác vụ đang chạy'
                }
                icon={Mic}
              />
              <StatCard
                label='Dung lượng đã dùng'
                value={formatBytes(stats.total_bytes)}
                hint={stats.failed > 0 ? `${stats.failed} video gặp lỗi` : undefined}
                icon={stats.failed > 0 ? TriangleAlert : HardDrive}
                tone={stats.failed > 0 ? 'warning' : 'default'}
              />
            </div>
          )
        )}

        <div className='mt-6 grid gap-4 lg:grid-cols-3'>
          <Card className='lg:col-span-2'>
            <CardHeader>
              <div className='flex items-center justify-between'>
                <div>
                  <CardTitle className='text-base'>Video gần đây</CardTitle>
                  <CardDescription>
                    Video mới tải về, bấm để xử lý tiếp.
                  </CardDescription>
                </div>
                <Button asChild size='sm' variant='outline'>
                  <Link to='/videos'>Xem tất cả</Link>
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {recent.length === 0 ? (
                <p className='py-6 text-center text-sm text-muted-foreground'>
                  Chưa có video nào. Bắt đầu từ Xu hướng hoặc Tìm &amp; tải.
                </p>
              ) : (
                <ul className='space-y-3'>
                  {recent.map((video) => (
                    <li key={video.video_id}>
                      <Link
                        to='/videos'
                        className='flex items-center gap-3 rounded-lg p-1 hover:bg-accent'
                      >
                        <CoverImage
                          src={video.cover_url}
                          className='w-24 shrink-0 rounded'
                        />
                        <div className='min-w-0 flex-1'>
                          <p className='line-clamp-2 text-sm'>{video.title}</p>
                          <p className='text-xs text-muted-foreground'>
                            {formatBytes(video.total_bytes)} · {video.files.length} file
                          </p>
                        </div>
                        <Badge
                          variant={
                            video.status.startsWith('failed_') ? 'destructive' : 'outline'
                          }
                          className='shrink-0 text-[11px]'
                        >
                          {video.status}
                        </Badge>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className='text-base'>Bắt đầu nhanh</CardTitle>
              <CardDescription>Luồng làm việc thường dùng.</CardDescription>
            </CardHeader>
            <CardContent className='space-y-2'>
              <Button asChild variant='outline' className='w-full justify-start'>
                <Link to='/trending'>
                  <TrendingUp className='size-4' />
                  Xem video đang hot
                </Link>
              </Button>
              <Button asChild variant='outline' className='w-full justify-start'>
                <Link to='/crawl'>
                  <Download className='size-4' />
                  Tìm video theo từ khoá
                </Link>
              </Button>
              <Button asChild variant='outline' className='w-full justify-start'>
                <Link to='/videos'>
                  <Clapperboard className='size-4' />
                  Xử lý video đã tải
                </Link>
              </Button>
              <Button asChild variant='outline' className='w-full justify-start'>
                <Link to='/api-keys'>
                  <Languages className='size-4' />
                  Cấu hình nhà cung cấp AI
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </Main>
    </>
  )
}
