import { Fragment, useEffect, useMemo, useState } from 'react'
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
} from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import {
  Download,
  ExternalLink,
  Flame,
  Loader2,
  MessageSquare,
  PlayCircle,
} from 'lucide-react'
import { toast } from 'sonner'
import {
  createJobFromSelection,
  type TrendingPage,
  type TrendingVideo,
} from '@/lib/api'
import { formatCompact, formatDuration, formatRelativeDate } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useInfiniteScroll } from '@/hooks/use-infinite-scroll'
import { useVideoTaskProgress } from '@/hooks/use-task-progress'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { CoverImage } from '@/components/cover-image'
import { VideoPreviewDialog } from '@/components/video-preview-dialog'

function bilibiliVideoUrl(bvid: string) {
  return `https://www.bilibili.com/video/${bvid}`
}

function bilibiliEmbedUrl(bvid: string) {
  return `https://player.bilibili.com/player.html?bvid=${bvid}&page=1&high_quality=1&danmaku=0`
}

/** Gộp id/trạng thái thật của các video vừa được backend tạo/xác nhận vào
 * cache của lưới đang hiển thị — để thẻ chuyển sang "đang tải" ngay lập tức,
 * không phải đợi vòng refetch tiếp theo (Phase 20). */
function mergeLibraryStatus(
  queryKey: unknown[],
  matched: { bvid: string; video_id: number }[],
  queryClient: ReturnType<typeof useQueryClient>
) {
  const byBvid = new Map(matched.map((v) => [v.bvid, v.video_id]))
  queryClient.setQueryData<InfiniteData<TrendingPage>>(queryKey, (old) => {
    if (!old) return old
    return {
      ...old,
      pages: old.pages.map((page) => ({
        ...page,
        videos: page.videos.map((v) => {
          const videoId = byBvid.get(v.bvid)
          return videoId === undefined
            ? v
            : { ...v, video_id: videoId, already_in_library: true }
        }),
      })),
    }
  })
}

/** 1 thẻ video trong lưới — tự đồng bộ trạng thái tải qua SSE (`useVideoTaskProgress`)
 * khi đã có `video_id`. Trước Phase 20, tải chỉ làm được ở trang Crawl riêng
 * (bảng, không phải lưới) sau khi đã tick chọn ở đây rồi "thêm vào hàng đợi" —
 * hàng đợi đó không có màn hình nào hiển thị lại được, xem
 * docs/phases/phase-20-discovery-workspace.md mục Khảo sát điểm 1. */
// Export để test riêng hành vi hiện trạng thái tải (không phải render cả lưới).
export function VideoCard({
  video,
  isPicked,
  onToggle,
  onPreview,
  onDownloadOne,
  downloadingOne,
}: {
  video: TrendingVideo
  isPicked: boolean
  onToggle: () => void
  onPreview: () => void
  onDownloadOne: () => void
  downloadingOne: boolean
}) {
  const task = useVideoTaskProgress(video.video_id ?? -1, 'download')
  const relativeDate = formatRelativeDate(video.published_at)

  return (
    <Card
      onClick={onToggle}
      className={cn(
        'relative cursor-pointer gap-3 overflow-hidden pt-0 transition-colors',
        isPicked && 'ring-2 ring-primary'
      )}
    >
      <Checkbox
        checked={isPicked}
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
        <div className='absolute inset-0 flex items-center justify-center gap-2 bg-black/0 opacity-0 transition-all group-hover/cover:bg-black/30 group-hover/cover:opacity-100'>
          <Button
            type='button'
            size='icon'
            variant='secondary'
            className='size-9 rounded-full shadow-sm'
            title='Xem nhanh trong popup'
            onClick={(e) => {
              e.stopPropagation()
              onPreview()
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
              window.open(bilibiliVideoUrl(video.bvid), '_blank', 'noopener,noreferrer')
            }}
          >
            <ExternalLink className='size-4' />
          </Button>
        </div>
      </div>
      <CardHeader>
        <CardTitle className='line-clamp-2 text-sm'>{video.title}</CardTitle>
      </CardHeader>
      <CardContent className='flex flex-col gap-1.5 text-xs text-muted-foreground'>
        <div className='flex items-center justify-between'>
          <span className='truncate'>{video.author_name ?? '—'}</span>
          <span className='shrink-0'>{formatDuration(video.duration_seconds)}</span>
        </div>
        <div className='flex items-center justify-between'>
          <span className='flex items-center gap-2'>
            {video.comment_count !== null && (
              <span className='flex items-center gap-0.5'>
                <MessageSquare className='size-3' />
                {formatCompact(video.comment_count)}
              </span>
            )}
            {video.coin_count !== null && <span>{formatCompact(video.coin_count)} xu</span>}
          </span>
          {relativeDate && <span className='shrink-0'>{relativeDate}</span>}
        </div>

        {/* Trạng thái tải — 3 nhánh: chưa tải / đang tải (SSE) / đã có sẵn.
            `already_in_library` chỉ nghĩa là "có bản ghi trong DB", không phân
            biệt được trạng thái pipeline xa hơn — task SSE mới nói được có
            đang chạy hay không, còn lại coi là "đã có sẵn". */}
        {video.video_id === null && (
          <Button
            type='button'
            size='sm'
            variant='outline'
            className='mt-1 w-fit'
            disabled={downloadingOne}
            onClick={(e) => {
              e.stopPropagation()
              onDownloadOne()
            }}
          >
            {downloadingOne ? (
              <Loader2 className='size-3.5 animate-spin' />
            ) : (
              <Download className='size-3.5' />
            )}
            Tải video
          </Button>
        )}
        {video.video_id !== null && task?.is_running && (
          <div className='mt-1 space-y-0.5' onClick={(e) => e.stopPropagation()}>
            <div className='h-1 overflow-hidden rounded-full bg-muted'>
              <div
                data-testid='discover-download-progress-bar'
                className='h-full rounded-full bg-primary transition-[width] duration-300'
                style={{ width: `${Math.min(100, Math.max(0, task.percent))}%` }}
              />
            </div>
            <span className='text-[10px] tabular-nums'>
              {task.stage_label} · {Math.round(task.percent)}%
            </span>
          </div>
        )}
        {video.video_id !== null && !task?.is_running && (
          <Link
            to='/videos/$videoId'
            params={{ videoId: String(video.video_id) }}
            onClick={(e) => e.stopPropagation()}
            className='mt-1 w-fit text-xs text-primary hover:underline'
          >
            Đã có trong thư viện → Video của tôi
          </Link>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * Lưới video dùng chung cho 3 nguồn dữ liệu: xếp hạng theo chuyên mục, danh
 * sách phổ biến toàn trang ("Tất cả"), và tìm kiếm tự do — chỉ khác nhau ở
 * hàm tải trang, còn lại (chọn video, xem trước, tải, ngăn cách nguồn) dùng chung.
 */
export function VideoGridPanel({
  queryKey,
  fetchPage,
}: {
  queryKey: unknown[]
  fetchPage: (page: number) => Promise<TrendingPage>
}) {
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [previewVideo, setPreviewVideo] = useState<TrendingVideo | null>(null)
  const [downloadingBvids, setDownloadingBvids] = useState<Set<string>>(new Set())

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
        if (page.source === 'search' && sawNonSearch && firstSearchBvid === null) {
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
    onSuccess: (job, picked) => {
      mergeLibraryStatus(
        queryKey,
        job.videos.map((v) => ({ bvid: v.platform_video_id, video_id: v.id })),
        queryClient
      )
      setSelected(new Set())
      setDownloadingBvids((prev) => {
        const next = new Set(prev)
        for (const v of picked) next.delete(v.bvid)
        return next
      })
      toast.success(
        `Đang tải ${job.videos.length} video — xem tiến độ ngay trên từng thẻ hoặc ở icon tác vụ trên thanh trên.`
      )
    },
    onError: (_err, picked) => {
      setDownloadingBvids((prev) => {
        const next = new Set(prev)
        for (const v of picked) next.delete(v.bvid)
        return next
      })
      toast.error('Không tải được. Kiểm tra backend đang chạy.')
    },
  })

  function toggle(bvid: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(bvid)) next.delete(bvid)
      else next.add(bvid)
      return next
    })
  }

  function downloadOne(video: TrendingVideo) {
    setDownloadingBvids((prev) => new Set(prev).add(video.bvid))
    createJob.mutate([video])
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
  const allSelected = Boolean(videos?.length) && selected.size === videos?.length

  return (
    <div className='space-y-4'>
      <div className='flex flex-wrap items-center gap-3'>
        <Button
          size='sm'
          disabled={pickedVideos.length === 0 || createJob.isPending}
          onClick={() => {
            setDownloadingBvids((prev) => {
              const next = new Set(prev)
              for (const v of pickedVideos) next.add(v.bvid)
              return next
            })
            createJob.mutate(pickedVideos)
          }}
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
            setSelected(allSelected ? new Set() : new Set(videos?.map((v) => v.bvid)))
          }
        >
          {allSelected ? 'Bỏ chọn tất cả' : 'Chọn tất cả'}
        </Button>
        {selected.size > 0 && (
          <span className='text-sm text-muted-foreground'>Đã chọn {selected.size}</span>
        )}
      </div>

      <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'>
        {videos?.map((video) => (
          <Fragment key={video.bvid}>
            {video.bvid === firstSearchBvid && (
              <div className='col-span-full -mb-1 flex items-center gap-2 pt-2 text-xs text-muted-foreground'>
                <div className='h-px flex-1 bg-border' />
                <span>
                  Duyệt thêm theo chuyên mục — không phải bảng xếp hạng, có thể lẫn
                  video không liên quan
                </span>
                <div className='h-px flex-1 bg-border' />
              </div>
            )}
            <VideoCard
              video={video}
              isPicked={selected.has(video.bvid)}
              onToggle={() => toggle(video.bvid)}
              onPreview={() => setPreviewVideo(video)}
              onDownloadOne={() => downloadOne(video)}
              downloadingOne={downloadingBvids.has(video.bvid)}
            />
          </Fragment>
        ))}
      </div>

      {/* Sentinel: lọt vào tầm nhìn thì tải trang tiếp theo. */}
      <div ref={sentinelRef} className='h-px' />

      {isFetchingNextPage && (
        <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'>
          {Array.from({ length: 4 }, (_, i) => (
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
        bvid={previewVideo?.bvid ?? null}
        channelId={previewVideo?.channel_id ?? null}
        channelName={previewVideo?.author_name ?? null}
        channelIsFollowed={previewVideo?.channel_is_followed ?? false}
        onSelectVideo={setPreviewVideo}
      />
    </div>
  )
}
