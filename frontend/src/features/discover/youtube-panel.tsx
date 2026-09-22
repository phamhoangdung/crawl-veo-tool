import { useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { ExternalLink, Loader2, PlayCircle } from 'lucide-react'
import {
  getYoutubeCategories,
  getYoutubeStatus,
  getYoutubeTrending,
  type YoutubeVideo,
} from '@/lib/api'
import { useInfiniteScroll } from '@/hooks/use-infinite-scroll'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatCompact, formatRelativeDate } from '@/lib/format'
import { CoverImage } from '@/components/cover-image'
import { VideoPreviewDialog } from '@/components/video-preview-dialog'

function youtubeVideoUrl(videoId: string) {
  return `https://www.youtube.com/watch?v=${videoId}`
}

function youtubeEmbedUrl(videoId: string) {
  return `https://www.youtube.com/embed/${videoId}`
}

/** Chỉ để XEM xu hướng lấy ý tưởng — không có checkbox/tải video (khác
 * Bilibili). Người dùng đã xác nhận rõ: "ytb chỉ là để xem xu hướng thôi,
 * chứ ko lấy video về". */
function CategoryVideos({ categoryId }: { categoryId: string | null }) {
  const [previewVideo, setPreviewVideo] = useState<YoutubeVideo | null>(null)

  const {
    data,
    isLoading,
    isError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['trending', 'youtube', 'trending', categoryId],
    queryFn: ({ pageParam }: { pageParam: string | null }) =>
      getYoutubeTrending('VN', categoryId, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.next_page_token : undefined,
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  })

  const videos = data?.pages.flatMap((page) => page.videos) ?? []

  const sentinelRef = useInfiniteScroll({
    enabled: Boolean(hasNextPage) && !isFetchingNextPage,
    onReachEnd: fetchNextPage,
  })

  if (isLoading) {
    return (
      <p className='flex items-center gap-2 text-muted-foreground'>
        <Loader2 className='size-4 animate-spin' />
        Đang tải...
      </p>
    )
  }

  if (isError) {
    return (
      <p className='text-sm text-destructive'>
        Không tải được xu hướng YouTube. Kiểm tra API key ở trang API Keys.
      </p>
    )
  }

  return (
    <div className='space-y-4'>
      <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
        {videos.map((video) => {
          const relativeDate = formatRelativeDate(video.published_at)
          return (
            <Card
              key={video.video_id}
              className='relative gap-3 overflow-hidden pt-0'
            >
              <div className='group/cover relative'>
                <CoverImage src={video.thumbnail_url} className='w-full' />
                <div className='absolute inset-0 flex items-center justify-center gap-2 bg-black/0 opacity-0 transition-all group-hover/cover:bg-black/30 group-hover/cover:opacity-100'>
                  <Button
                    type='button'
                    size='icon'
                    variant='secondary'
                    className='size-9 rounded-full shadow-sm'
                    title='Xem nhanh trong popup'
                    onClick={() => setPreviewVideo(video)}
                  >
                    <PlayCircle className='size-5' />
                  </Button>
                  <Button
                    type='button'
                    size='icon'
                    variant='secondary'
                    className='size-9 rounded-full shadow-sm'
                    title='Mở trên YouTube'
                    onClick={() =>
                      window.open(
                        youtubeVideoUrl(video.video_id),
                        '_blank',
                        'noopener,noreferrer'
                      )
                    }
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
                <span className='truncate'>{video.channel_title}</span>
                <div className='flex items-center justify-between'>
                  <span>
                    {video.view_count !== null &&
                      `${formatCompact(video.view_count)} lượt xem`}
                  </span>
                  {relativeDate && (
                    <span className='shrink-0'>{relativeDate}</span>
                  )}
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

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
          Đã hết video.
        </p>
      )}

      <VideoPreviewDialog
        title={previewVideo?.title ?? null}
        embedUrl={previewVideo ? youtubeEmbedUrl(previewVideo.video_id) : null}
        externalUrl={previewVideo ? youtubeVideoUrl(previewVideo.video_id) : null}
        externalLabel='Mở trên YouTube'
        onClose={() => setPreviewVideo(null)}
      />
    </div>
  )
}

export function YoutubePanel() {
  const status = useQuery({
    queryKey: ['youtube', 'status'],
    queryFn: getYoutubeStatus,
  })

  const categories = useQuery({
    queryKey: ['trending', 'youtube', 'categories'],
    queryFn: () => getYoutubeCategories('VN'),
    enabled: status.data?.configured === true,
    retry: false,
  })

  if (status.isLoading) {
    return (
      <p className='flex items-center gap-2 text-muted-foreground'>
        <Loader2 className='size-4 animate-spin' />
        Đang tải...
      </p>
    )
  }

  if (!status.data?.configured) {
    return (
      <Alert>
        <AlertTitle>Chưa cấu hình YouTube Data API</AlertTitle>
        <AlertDescription>
          Tạo API key tại{' '}
          <a
            href='https://console.cloud.google.com/apis/credentials'
            target='_blank'
            rel='noopener noreferrer'
            className='underline'
          >
            console.cloud.google.com
          </a>{' '}
          (bật &quot;YouTube Data API v3&quot;), rồi thêm ở trang{' '}
          <a href='/api-keys' className='underline'>
            API Keys
          </a>{' '}
          với provider &quot;YouTube Data API&quot;. Miễn phí, chỉ giới hạn theo
          quota (10.000 unit/ngày).
        </AlertDescription>
      </Alert>
    )
  }

  if (categories.isError) {
    return (
      <p className='text-sm text-destructive'>
        Không tải được danh sách chuyên mục YouTube — kiểm tra lại API key.
      </p>
    )
  }

  return (
    <Tabs defaultValue='all'>
      <div className='overflow-x-auto'>
        <TabsList>
          <TabsTrigger value='all'>Tất cả</TabsTrigger>
          {categories.data?.map((category) => (
            <TabsTrigger key={category.id} value={category.id}>
              {category.name}
            </TabsTrigger>
          ))}
        </TabsList>
      </div>
      <TabsContent value='all' className='mt-4'>
        <CategoryVideos categoryId={null} />
      </TabsContent>
      {categories.data?.map((category) => (
        <TabsContent key={category.id} value={category.id} className='mt-4'>
          <CategoryVideos categoryId={category.id} />
        </TabsContent>
      ))}
    </Tabs>
  )
}
