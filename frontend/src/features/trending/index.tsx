import { Fragment, useEffect, useMemo, useState } from 'react'
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { ExternalLink, Flame, Loader2, MessageSquare, PlayCircle } from 'lucide-react'
import { toast } from 'sonner'
import {
  createJobFromSelection,
  getCategoryPage,
  getFollowedCategories,
  getPopularPage,
  getTrendingCategories,
  refreshCategories,
  searchBilibili,
  setFollowedCategories,
  type TrendingPage,
  type TrendingVideo,
} from '@/lib/api'
import { formatDuration } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useInfiniteScroll } from '@/hooks/use-infinite-scroll'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CoverImage } from '@/components/cover-image'
import { KeywordSearchBox } from '@/components/keyword-search-box'
import { AppHeader } from '@/components/layout/app-header'
import { Main } from '@/components/layout/main'
import { VideoPreviewDialog } from '@/components/video-preview-dialog'
import { CategoryChart } from './category-chart'
import { CategoryPicker } from './category-picker'
import { formatCompact, formatRelativeDate } from './format'
import { YoutubePanel } from './youtube-panel'

function bilibiliVideoUrl(bvid: string) {
  return `https://www.bilibili.com/video/${bvid}`
}

function bilibiliEmbedUrl(bvid: string) {
  return `https://player.bilibili.com/player.html?bvid=${bvid}&page=1&high_quality=1&danmaku=0`
}

/**
 * Lưới video dùng chung cho 3 nguồn dữ liệu: xếp hạng theo chuyên mục, danh
 * sách phổ biến toàn trang ("Tất cả"), và tìm kiếm tự do — chỉ khác nhau ở
 * hàm tải trang, còn lại (chọn video, xem trước, ngăn cách nguồn) dùng chung.
 */
function VideoGridPanel({
  queryKey,
  fetchPage,
}: {
  queryKey: unknown[]
  fetchPage: (page: number) => Promise<TrendingPage>
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [previewVideo, setPreviewVideo] = useState<TrendingVideo | null>(null)

  const {
    data,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    // `fetchPage` là prop, không phải state đóng gói giá trị ngoài `queryKey`:
    // mọi nơi gọi component này đều nhét đúng giá trị phân biệt (rid/từ khoá
    // tìm kiếm) vào CẢ `queryKey` lẫn closure của `fetchPage` cùng lúc — không
    // có nguy cơ lệch cache dù rule tĩnh không thấy được điều đó.
    // eslint-disable-next-line @tanstack/query/exhaustive-deps
  } = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) => fetchPage(pageParam),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.page + 1 : undefined,
    // Giữ dữ liệu đã xem trong 5 phút để quay lại tab không phải tải lại;
    // xếp hạng Bilibili đổi chậm nên không sợ lệch.
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  })

  // Trang "ranking"/"popular" (đúng nghĩa đang hot) và trang "search" (chỉ để
  // lướt thêm, có thể lẫn video không liên quan) có thể trả trùng video — lọc
  // trùng, đồng thời nhớ video đầu tiên đến từ search SAU ÍT NHẤT 1 trang
  // không phải search, để chèn ngăn cách rõ. Không chèn ngăn cách khi TOÀN BỘ
  // kết quả đều là search ngay từ trang 1 (tìm kiếm tự do) — lúc đó không có
  // gì để "so" với, ngăn cách sẽ vô nghĩa.
  const { videos, firstSearchBvid } = useMemo(() => {
    const seen = new Set<string>()
    const flat: TrendingVideo[] = []
    let firstSearchBvid: string | null = null
    let sawNonSearch = false
    for (const page of data?.pages ?? []) {
      for (const v of page.videos) {
        if (seen.has(v.bvid)) continue
        seen.add(v.bvid)
        flat.push(v)
        if (
          page.source === 'search' &&
          sawNonSearch &&
          firstSearchBvid === null
        ) {
          firstSearchBvid = v.bvid
        }
      }
      if (page.source !== 'search') sawNonSearch = true
    }
    return { videos: flat, firstSearchBvid }
  }, [data])

  // Chỉ trang đầu của nguồn "search" có bật dịch mới có field này — ranking/
  // popular luôn undefined, không hiện cảnh báo nhầm.
  const translationFailed = data?.pages[0]?.translation_failed ?? false
  useEffect(() => {
    if (translationFailed) {
      toast.warning(
        'Dịch từ khoá thất bại, đã tìm bằng nguyên văn (dễ ra ít/không có kết quả). Kiểm tra lại API key dịch trong Cài đặt.'
      )
    }
  }, [translationFailed])

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
    onError: () =>
      toast.error('Không tạo được job. Kiểm tra backend đang chạy.'),
  })

  function toggle(bvid: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(bvid)) next.delete(bvid)
      else next.add(bvid)
      return next
    })
  }

  if (isLoading) {
    return (
      <p className='flex items-center gap-2 text-muted-foreground'>
        <Loader2 className='size-4 animate-spin' />
        Đang tải...
      </p>
    )
  }

  const pickedVideos = videos?.filter((v) => selected.has(v.bvid)) ?? []
  const allSelected =
    Boolean(videos?.length) && selected.size === videos?.length

  return (
    <div className='space-y-4'>
      <div className='flex flex-wrap items-center gap-3'>
        <Button
          size='sm'
          disabled={pickedVideos.length === 0 || createJob.isPending}
          onClick={() => createJob.mutate(pickedVideos)}
        >
          {createJob.isPending && <Loader2 className='size-3.5 animate-spin' />}
          {createJob.isPending
            ? 'Đang thêm...'
            : `Tải ${pickedVideos.length || ''} video đã chọn`.trim()}
        </Button>
        <Button
          size='sm'
          variant='outline'
          onClick={() =>
            setSelected(
              allSelected ? new Set() : new Set(videos?.map((v) => v.bvid))
            )
          }
        >
          {allSelected ? 'Bỏ chọn tất cả' : 'Chọn tất cả'}
        </Button>
        {selected.size > 0 && (
          <span className='text-sm text-muted-foreground'>
            Đã chọn {selected.size}
          </span>
        )}
      </div>

      <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
        {videos?.map((video) => {
          const isPicked = selected.has(video.bvid)
          const relativeDate = formatRelativeDate(video.published_at)
          return (
            <Fragment key={video.bvid}>
              {video.bvid === firstSearchBvid && (
                <div className='col-span-full -mb-1 flex items-center gap-2 pt-2 text-xs text-muted-foreground'>
                  <div className='h-px flex-1 bg-border' />
                  <span>
                    Duyệt thêm theo chuyên mục — không phải bảng xếp hạng, có
                    thể lẫn video không liên quan
                  </span>
                  <div className='h-px flex-1 bg-border' />
                </div>
              )}
              {/* pt-0 + overflow-hidden: Card mặc định có py-6 nên ảnh dán sát
                  mép trên sẽ bị đẩy xuống, để lộ một khoảng trống thừa. */}
              <Card
                onClick={() => toggle(video.bvid)}
                className={cn(
                  'relative cursor-pointer gap-3 overflow-hidden pt-0 transition-colors',
                  isPicked && 'ring-2 ring-primary'
                )}
              >
                <Checkbox
                  checked={isPicked}
                  // Card đã bắt click cho cả thẻ; checkbox chỉ để hiển thị trạng thái.
                  tabIndex={-1}
                  className='absolute top-2 left-2 z-10 bg-background/80 shadow-sm'
                />
                {video.heat_score !== null && (
                  <span
                    title='Đang trong bảng xếp hạng thật của Bilibili'
                    className='absolute top-2 right-2 z-10 flex items-center gap-1 rounded-full bg-background/80 px-2 py-0.5 text-xs font-medium text-orange-500 shadow-sm'
                  >
                    <Flame className='size-3' />
                    Hot
                  </span>
                )}
                <div className='group/cover relative'>
                  <CoverImage src={video.cover_url} className='w-full' />
                  {/* Xem trước — dừng lan sự kiện để không bị Card bắt thành chọn/bỏ chọn. */}
                  <div className='absolute inset-0 flex items-center justify-center gap-2 bg-black/0 opacity-0 transition-all group-hover/cover:bg-black/30 group-hover/cover:opacity-100'>
                    <Button
                      type='button'
                      size='icon'
                      variant='secondary'
                      className='size-9 rounded-full shadow-sm'
                      title='Xem nhanh trong popup'
                      onClick={(e) => {
                        e.stopPropagation()
                        setPreviewVideo(video)
                      }}
                    >
                      <PlayCircle className='size-5' />
                    </Button>
                    <Button
                      type='button'
                      size='icon'
                      variant='secondary'
                      className='size-9 rounded-full shadow-sm'
                      title='Mở trên Bilibili'
                      onClick={(e) => {
                        e.stopPropagation()
                        window.open(
                          bilibiliVideoUrl(video.bvid),
                          '_blank',
                          'noopener,noreferrer'
                        )
                      }}
                    >
                      <ExternalLink className='size-4' />
                    </Button>
                  </div>
                </div>
                <CardHeader>
                  <CardTitle className='line-clamp-2 text-sm'>
                    {video.title}
                  </CardTitle>
                </CardHeader>
                <CardContent className='flex flex-col gap-1.5 text-xs text-muted-foreground'>
                  <div className='flex items-center justify-between'>
                    <span className='truncate'>{video.author_name ?? '—'}</span>
                    <span className='shrink-0'>
                      {formatDuration(video.duration_seconds)}
                    </span>
                  </div>
                  <div className='flex items-center justify-between'>
                    <span className='flex items-center gap-2'>
                      {video.comment_count !== null && (
                        <span className='flex items-center gap-0.5'>
                          <MessageSquare className='size-3' />
                          {formatCompact(video.comment_count)}
                        </span>
                      )}
                      {video.coin_count !== null && (
                        <span>{formatCompact(video.coin_count)} xu</span>
                      )}
                    </span>
                    {relativeDate && (
                      <span className='shrink-0'>{relativeDate}</span>
                    )}
                  </div>
                </CardContent>
              </Card>
            </Fragment>
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

      <VideoPreviewDialog
        title={previewVideo?.title ?? null}
        embedUrl={previewVideo ? bilibiliEmbedUrl(previewVideo.bvid) : null}
        externalUrl={previewVideo ? bilibiliVideoUrl(previewVideo.bvid) : null}
        externalLabel='Mở trên Bilibili'
        onClose={() => setPreviewVideo(null)}
      />
    </div>
  )
}

export function Trending() {
  const queryClient = useQueryClient()
  const [platform, setPlatform] = useState<'bilibili' | 'youtube'>('bilibili')
  const [searchInput, setSearchInput] = useState('')
  const [activeSearch, setActiveSearch] = useState('')
  const [translateKeyword, setTranslateKeyword] = useState(true)

  // Chuyên mục chưa dịch (name === name_zh, xem `CategoryRead` — name đã ưu
  // tiên name_vi) sẽ được backend tự dịch NỀN mỗi lần gọi GET /categories
  // (xem `_queue_translation_if_pending`) — poll nhẹ trong lúc còn mục chưa
  // dịch để tên tiếng Việt tự hiện ra dần, không cần bấm lại "Quét chuyên mục".
  const { data: categories } = useQuery({
    queryKey: ['trending', 'bilibili', 'categories'],
    queryFn: getTrendingCategories,
    refetchInterval: (query) => {
      const pending =
        query.state.data?.some((c) => c.name === c.name_zh) ?? false
      return pending ? 8000 : false
    },
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
      <AppHeader />

      <Main>
        <div className='mb-4 flex flex-wrap items-start justify-between gap-3'>
          <div>
            <h1 className='text-2xl font-bold tracking-tight'>Trending</h1>
            <p className='text-muted-foreground'>
              {platform === 'bilibili'
                ? 'Video đang hot trên Bilibili theo từng chuyên mục — dùng để chọn từ khoá crawl.'
                : 'Xu hướng YouTube — chỉ để tham khảo ý tưởng, không tải video ở đây.'}
            </p>
          </div>
          <div className='flex items-center gap-2'>
            {platform === 'bilibili' && (
              <>
                <Button
                  variant='ghost'
                  size='sm'
                  disabled={refresh.isPending}
                  onClick={() => refresh.mutate()}
                >
                  {refresh.isPending && (
                    <Loader2 className='size-3.5 animate-spin' />
                  )}
                  {refresh.isPending ? 'Đang quét...' : 'Quét chuyên mục mới'}
                </Button>
                {categories && (
                  <CategoryPicker
                    categories={categories}
                    selected={selectedRids}
                    onChange={(rids) => saveFollowed.mutate(rids)}
                  />
                )}
              </>
            )}
          </div>
        </div>

        <div className='mb-4 flex w-fit gap-1 rounded-lg border bg-muted/50 p-1'>
          <Button
            type='button'
            size='sm'
            variant={platform === 'bilibili' ? 'default' : 'ghost'}
            onClick={() => setPlatform('bilibili')}
          >
            Bilibili
          </Button>
          <Button
            type='button'
            size='sm'
            variant={platform === 'youtube' ? 'default' : 'ghost'}
            onClick={() => setPlatform('youtube')}
          >
            YouTube
          </Button>
        </div>

        {platform === 'youtube' ? (
          <YoutubePanel />
        ) : (
          <>
            <KeywordSearchBox
              className='mb-4'
              inputClassName='max-w-md'
              value={searchInput}
              onChange={setSearchInput}
              onSubmit={() => setActiveSearch(searchInput.trim())}
              placeholder='Tìm video theo từ khoá bất kỳ, không giới hạn chuyên mục...'
              translateKeyword={translateKeyword}
              onTranslateKeywordChange={setTranslateKeyword}
              onClear={
                activeSearch
                  ? () => {
                      setActiveSearch('')
                      setSearchInput('')
                    }
                  : undefined
              }
            />

            {activeSearch ? (
              <div className='space-y-4'>
                <p className='text-sm text-muted-foreground'>
                  Kết quả tìm kiếm cho &quot;{activeSearch}&quot; — không phải
                  bảng xếp hạng, có thể lẫn video không liên quan.
                </p>
                <VideoGridPanel
                  queryKey={[
                    'trending',
                    'bilibili',
                    'search',
                    activeSearch,
                    translateKeyword,
                  ]}
                  fetchPage={(page) =>
                    searchBilibili(activeSearch, page, { translateKeyword })
                  }
                />
              </div>
            ) : (
              <>
                <div className='mb-6'>
                  <CategoryChart rids={selectedRids} />
                </div>

                <Tabs defaultValue='all'>
                  <div className='overflow-x-auto'>
                    <TabsList>
                      <TabsTrigger value='all'>Tất cả</TabsTrigger>
                      {activeCategories.map((category) => (
                        <TabsTrigger
                          key={category.rid}
                          value={String(category.rid)}
                        >
                          {category.name}
                        </TabsTrigger>
                      ))}
                    </TabsList>
                  </div>
                  <TabsContent value='all' className='mt-4'>
                    <VideoGridPanel
                      queryKey={['trending', 'bilibili', 'popular-page']}
                      fetchPage={getPopularPage}
                    />
                  </TabsContent>
                  {activeCategories.map((category) => (
                    <TabsContent
                      key={category.rid}
                      value={String(category.rid)}
                      className='mt-4'
                    >
                      <VideoGridPanel
                        queryKey={[
                          'trending',
                          'bilibili',
                          'category-page',
                          category.rid,
                        ]}
                        fetchPage={(page) =>
                          getCategoryPage(category.rid, page)
                        }
                      />
                    </TabsContent>
                  ))}
                </Tabs>
              </>
            )}
          </>
        )}
      </Main>
    </>
  )
}
