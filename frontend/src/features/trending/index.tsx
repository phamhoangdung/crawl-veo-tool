import { useMemo, useState } from 'react'
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  createJobFromSelection,
  getCategoryPage,
  getFollowedCategories,
  getTrendingCategories,
  refreshCategories,
  setFollowedCategories,
  type TrendingVideo,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { useInfiniteScroll } from '@/hooks/use-infinite-scroll'
import { CoverImage } from '@/components/cover-image'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { CategoryChart } from './category-chart'
import { CategoryPicker } from './category-picker'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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

function CategoryPanel({ rid }: { rid: number }) {
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const {
    data,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['trending', 'bilibili', 'category-page', rid],
    queryFn: ({ pageParam }) => getCategoryPage(rid, pageParam),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.page + 1 : undefined,
    // Giữ dữ liệu chuyên mục đã xem trong 5 phút để quay lại tab không phải
    // tải lại; xếp hạng Bilibili đổi chậm nên không sợ lệch.
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  })

  // Ranking (trang 1) và search (trang sau) có thể trả trùng video.
  const videos = useMemo(() => {
    const seen = new Set<string>()
    return (data?.pages ?? []).flatMap((page) =>
      page.videos.filter((v) => {
        if (seen.has(v.bvid)) return false
        seen.add(v.bvid)
        return true
      })
    )
  }, [data])

  const sentinelRef = useInfiniteScroll({
    enabled: Boolean(hasNextPage) && !isFetchingNextPage,
    onReachEnd: fetchNextPage,
  })

  const createJob = useMutation({
    mutationFn: (picked: TrendingVideo[]) => createJobFromSelection(picked),
    onSuccess: (job) => {
      setSelected(new Set())
      toast.success(
        `Đã thêm ${job.videos.length} video vào hàng đợi. Mở trang Crawl để tải.`
      )
    },
    onError: () => toast.error('Không tạo được job. Kiểm tra backend đang chạy.'),
  })

  function toggle(bvid: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(bvid)) next.delete(bvid)
      else next.add(bvid)
      return next
    })
  }

  if (isLoading) return <p className='text-muted-foreground'>Đang tải...</p>

  const pickedVideos = videos?.filter((v) => selected.has(v.bvid)) ?? []
  const allSelected = Boolean(videos?.length) && selected.size === videos?.length

  return (
    <div className='space-y-4'>
      <div className='flex flex-wrap items-center gap-3'>
        <Button
          size='sm'
          disabled={pickedVideos.length === 0 || createJob.isPending}
          onClick={() => createJob.mutate(pickedVideos)}
        >
          {createJob.isPending
            ? 'Đang thêm...'
            : `Tải ${pickedVideos.length || ''} video đã chọn`.trim()}
        </Button>
        <Button
          size='sm'
          variant='outline'
          onClick={() =>
            setSelected(allSelected ? new Set() : new Set(videos?.map((v) => v.bvid)))
          }
        >
          {allSelected ? 'Bỏ chọn tất cả' : 'Chọn tất cả'}
        </Button>
        {selected.size > 0 && (
          <span className='text-sm text-muted-foreground'>Đã chọn {selected.size}</span>
        )}
      </div>

      <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
        {videos?.map((video) => {
          const isPicked = selected.has(video.bvid)
          return (
            // pt-0 + overflow-hidden: Card mặc định có py-6 nên ảnh dán sát mép
            // trên sẽ bị đẩy xuống, để lộ một khoảng trống thừa.
            <Card
              key={video.bvid}
              onClick={() => toggle(video.bvid)}
              className={cn(
                'relative cursor-pointer gap-4 overflow-hidden pt-0 transition-colors',
                isPicked && 'ring-2 ring-primary'
              )}
            >
              <Checkbox
                checked={isPicked}
                // Card đã bắt click cho cả thẻ; checkbox chỉ để hiển thị trạng thái.
                tabIndex={-1}
                className='absolute top-2 left-2 z-10 bg-background/80 shadow-sm'
              />
              <CoverImage src={video.cover_url} className='w-full' />
              <CardHeader>
                <CardTitle className='line-clamp-2 text-sm'>{video.title}</CardTitle>
              </CardHeader>
              <CardContent className='flex items-center justify-between text-xs text-muted-foreground'>
                <span>{video.author_name ?? '—'}</span>
                <span>{formatDuration(video.duration_seconds)}</span>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* Sentinel: lọt vào tầm nhìn thì tải trang tiếp theo. */}
      <div ref={sentinelRef} className='h-px' />

      {isFetchingNextPage && (
        <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className='h-64 w-full rounded-xl' />
          ))}
        </div>
      )}

      {!hasNextPage && videos.length > 0 && (
        <p className='py-2 text-center text-sm text-muted-foreground'>
          Đã hết video trong chuyên mục này.
        </p>
      )}
    </div>
  )
}

export function Trending() {
  const queryClient = useQueryClient()

  const { data: categories } = useQuery({
    queryKey: ['trending', 'bilibili', 'categories'],
    queryFn: getTrendingCategories,
  })

  // Lựa chọn lưu ở DB (không phải localStorage) để giữ nguyên khi đóng gói
  // thành app desktop và khi mở từ máy khác.
  const { data: followedRids } = useQuery({
    queryKey: ['trending', 'bilibili', 'followed'],
    queryFn: getFollowedCategories,
  })

  const saveFollowed = useMutation({
    mutationFn: setFollowedCategories,
    onSuccess: (rids) => {
      queryClient.setQueryData(['trending', 'bilibili', 'followed'], rids)
    },
    onError: () => toast.error('Không lưu được lựa chọn chuyên mục.'),
  })

  const refresh = useMutation({
    mutationFn: refreshCategories,
    onSuccess: (all) => {
      queryClient.setQueryData(['trending', 'bilibili', 'categories'], all)
      toast.success(`Đã cập nhật ${all.length} chuyên mục từ Bilibili.`)
    },
    onError: () => toast.error('Không quét được chuyên mục mới.'),
  })

  const selectedRids = followedRids ?? []
  const activeCategories =
    categories?.filter((c) => selectedRids.includes(c.rid)) ?? []

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
        <div className='mb-4 flex flex-wrap items-start justify-between gap-3'>
          <div>
            <h1 className='text-2xl font-bold tracking-tight'>Trending</h1>
            <p className='text-muted-foreground'>
              Video đang hot trên Bilibili theo từng chuyên mục — dùng để chọn từ khoá crawl.
            </p>
          </div>
          <div className='flex items-center gap-2'>
            <Button
              variant='ghost'
              size='sm'
              disabled={refresh.isPending}
              onClick={() => refresh.mutate()}
            >
              {refresh.isPending ? 'Đang quét...' : 'Quét chuyên mục mới'}
            </Button>
            {categories && (
              <CategoryPicker
                categories={categories}
                selected={selectedRids}
                onChange={(rids) => saveFollowed.mutate(rids)}
              />
            )}
          </div>
        </div>

        <div className='mb-6'>
          <CategoryChart rids={selectedRids} />
        </div>

        {activeCategories.length > 0 ? (
          <Tabs defaultValue={String(activeCategories[0].rid)}>
            <div className='overflow-x-auto'>
              <TabsList>
                {activeCategories.map((category) => (
                  <TabsTrigger key={category.rid} value={String(category.rid)}>
                    {category.name}
                  </TabsTrigger>
                ))}
              </TabsList>
            </div>
            {activeCategories.map((category) => (
              <TabsContent key={category.rid} value={String(category.rid)} className='mt-4'>
                <CategoryPanel rid={category.rid} />
              </TabsContent>
            ))}
          </Tabs>
        ) : (
          <p className='text-muted-foreground'>
            Chưa chọn chuyên mục nào. Bấm &quot;Chọn chuyên mục&quot; để bắt đầu.
          </p>
        )}
      </Main>
    </>
  )
}
