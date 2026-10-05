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
  PanelRightClose,
  PanelRightOpen,
  PlayCircle,
  X,
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
import { BrandLoader } from '@/components/brand-loader'
import { CoverImage } from '@/components/cover-image'
import { VideoPreviewDialog } from '@/components/video-preview-dialog'

const CART_VISIBLE_KEY = 'discover.selectedCartVisible'

function bilibiliVideoUrl(bvid: string) {
  return `https://www.bilibili.com/video/${bvid}`
}

function bilibiliEmbedUrl(bvid: string) {
  return `https://player.bilibili.com/player.html?bvid=${bvid}&page=1&high_quality=1&danmaku=0`
}

/** Merge the real id/state of the videos just created/confirmed by the backend into
 * the cache of the grid currently displayed — so the card switches to "downloading" immediately,
 * without waiting for the next refetch round (Phase 20). */
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

/** 1 video card in the grid — syncs its download state itself over SSE (`useVideoTaskProgress`)
 * once it has a `video_id`. Before Phase 20, downloading was only possible on the separate Crawl page
 * (a table, not a grid) after ticking here and then "add to queue" —
 * that queue had no screen that could show it again, see
 * docs/phases/phase-20-discovery-workspace.md, Survey point 1. */
// Exported so the download-state display behavior can be tested separately (without rendering the whole grid).
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
        <CardTitle className='line-clamp-2 text-sm'>{video.title}</CardTitle>
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
          {relativeDate && <span className='shrink-0'>{relativeDate}</span>}
        </div>

        {/* Download state — 3 branches: not downloaded / downloading (SSE) / already available.
            `already_in_library` only means "has a record in the DB", it cannot
            tell further pipeline states apart — only the SSE task can say whether
            it is running, everything else counts as "already available". */}
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
          <div
            className='mt-1 space-y-0.5'
            onClick={(e) => e.stopPropagation()}
          >
            <div className='h-1 overflow-hidden rounded-full bg-muted'>
              <div
                data-testid='discover-download-progress-bar'
                className='h-full rounded-full bg-primary transition-[width] duration-300'
                style={{
                  width: `${Math.min(100, Math.max(0, task.percent))}%`,
                }}
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
 * The "selected" panel on the right (can be shown/hidden) — user feedback: picking many videos in one
 * long grid and then having to scroll back from the top to see what was picked. Only shown when
 * at least 1 video is selected (takes no space when unused), stays put while
 * scrolling (`sticky`) so the list + download button are always visible without searching again.
 */
// Exported to test separately (without building the whole VideoGridPanel + mocking the infinite query).
export function SelectedVideosCart({
  videos,
  onRemove,
  onClear,
  onDownload,
  isDownloading,
  onHide,
}: {
  videos: TrendingVideo[]
  onRemove: (bvid: string) => void
  onClear: () => void
  onDownload: () => void
  isDownloading: boolean
  /** When present, shows a collapse button for the panel (the list is kept, only hidden from the screen). */
  onHide?: () => void
}) {
  return (
    <aside className='sticky top-4 w-full shrink-0 space-y-3 self-start rounded-lg border bg-card p-3 sm:w-64'>
      <div className='flex items-center justify-between'>
        <span className='text-sm font-medium'>Đã chọn {videos.length}</span>
        <div className='flex items-center gap-2'>
          <button
            type='button'
            onClick={onClear}
            className='text-xs text-muted-foreground hover:underline'
          >
            Bỏ chọn tất cả
          </button>
          {onHide && (
            <button
              type='button'
              title='Ẩn danh sách đã chọn'
              aria-label='Ẩn danh sách đã chọn'
              onClick={onHide}
              className='text-muted-foreground hover:text-foreground'
            >
              <PanelRightClose className='size-4' />
            </button>
          )}
        </div>
      </div>

      <div className='max-h-[50vh] space-y-2 overflow-y-auto pr-1'>
        {videos.map((v) => (
          <div key={v.bvid} className='flex items-center gap-2'>
            <CoverImage src={v.cover_url} className='w-14 shrink-0 rounded' />
            <p className='line-clamp-2 flex-1 text-xs'>{v.title}</p>
            <button
              type='button'
              title='Bỏ chọn'
              onClick={() => onRemove(v.bvid)}
              className='shrink-0 text-muted-foreground hover:text-destructive'
            >
              <X className='size-3.5' />
            </button>
          </div>
        ))}
      </div>

      <Button
        size='sm'
        className='w-full'
        disabled={isDownloading}
        onClick={onDownload}
      >
        {isDownloading && <Loader2 className='size-3.5 animate-spin' />}
        {isDownloading ? 'Đang thêm...' : `Tải ${videos.length} video đã chọn`}
      </Button>
    </aside>
  )
}

/**
 * A video grid shared by 3 data sources: ranking by category, the site-wide
 * popular list ("All"), and free search — they differ only in the
 * page-loading function, everything else (selecting videos, preview, download, source separator) is shared.
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
  // Remember the show/hide choice of the "selected" panel between app launches.
  const [showCart, setShowCart] = useState(() => {
    try {
      return localStorage.getItem(CART_VISIBLE_KEY) !== '0'
    } catch {
      return true
    }
  })
  const setCartVisible = (visible: boolean) => {
    setShowCart(visible)
    try {
      localStorage.setItem(CART_VISIBLE_KEY, visible ? '1' : '0')
    } catch {
      // localStorage is unavailable (private mode...) — only the remembered choice is lost.
    }
  }
  const [previewVideo, setPreviewVideo] = useState<TrendingVideo | null>(null)
  const [downloadingBvids, setDownloadingBvids] = useState<Set<string>>(
    new Set()
  )

  const {
    data,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    // `fetchPage` is a prop, not state that packages a value outside `queryKey`:
    // every caller of this component puts the distinguishing value (rid/search
    // keyword) into BOTH `queryKey` and the `fetchPage` closure at the same time — there is
    // no risk of a cache mismatch even though the static rule cannot see that.
    // eslint-disable-next-line @tanstack/query/exhaustive-deps
  } = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) => fetchPage(pageParam),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.page + 1 : undefined,
    // Keep viewed data for 5 minutes so returning to the tab does not reload;
    // the Bilibili ranking changes slowly so there is no fear of drift.
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  })

  // "ranking"/"popular" pages (truly hot) and "search" pages (only for
  // scrolling further, may mix in unrelated videos) can return duplicate videos — dedupe
  // them, and also remember the first video coming from search AFTER AT LEAST 1 page
  // that is not search, to insert a clear separator. No separator is inserted when ALL
  // results are search from page 1 (free search) — there is then nothing
  // to "compare" against, and a separator would be meaningless.
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

  // Only the first page of a "search" source with translation on has this field — ranking/
  // popular is always undefined, so no warning is shown wrongly.
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
      // The preview popup (if open on exactly the video just downloaded) does not read from the
      // grid cache — sync by hand so the % bar shows right away in the popup, without having to close the
      // popup to see it downloading.
      setPreviewVideo((prev) => {
        if (!prev) return prev
        const match = job.videos.find((v) => v.platform_video_id === prev.bvid)
        return match
          ? { ...prev, video_id: match.id, already_in_library: true }
          : prev
      })
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

  function downloadMany(picked: TrendingVideo[]) {
    setDownloadingBvids((prev) => {
      const next = new Set(prev)
      for (const v of picked) next.add(v.bvid)
      return next
    })
    createJob.mutate(picked)
  }

  if (isLoading) {
    return <BrandLoader size='sm' />
  }

  const pickedVideos = videos?.filter((v) => selected.has(v.bvid)) ?? []
  const allSelected =
    Boolean(videos?.length) && selected.size === videos?.length

  return (
    <div className='space-y-4'>
      <div className='flex flex-wrap items-center gap-3'>
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
        {selected.size > 0 && (
          <Button
            size='sm'
            variant='ghost'
            className='ms-auto'
            onClick={() => setCartVisible(!showCart)}
          >
            {showCart ? (
              <PanelRightClose className='size-4' />
            ) : (
              <PanelRightOpen className='size-4' />
            )}
            {showCart ? 'Ẩn danh sách đã chọn' : 'Hiện danh sách đã chọn'}
          </Button>
        )}
      </div>

      {/* The "selected" panel stays put on the right while scrolling — user feedback:
          previously after picking many videos in a long grid you had to scroll back from the top
          to see what was picked, and the download button was only at the top of the page. */}
      <div className='flex flex-col items-start gap-4 sm:flex-row'>
        <div className='min-w-0 flex-1 space-y-4'>
          <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5'>
            {videos?.map((video) => (
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

          {/* Sentinel: when it enters view, load the next page. */}
          <div ref={sentinelRef} className='h-px' />

          {isFetchingNextPage && (
            <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5'>
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
        </div>

        {selected.size > 0 && showCart && (
          <SelectedVideosCart
            videos={pickedVideos}
            onRemove={toggle}
            onClear={() => setSelected(new Set())}
            onDownload={() => downloadMany(pickedVideos)}
            isDownloading={createJob.isPending}
            onHide={() => setCartVisible(false)}
          />
        )}
      </div>

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
        videoId={previewVideo?.video_id ?? null}
        onDownload={() => previewVideo && downloadOne(previewVideo)}
        isDownloading={
          previewVideo ? downloadingBvids.has(previewVideo.bvid) : false
        }
      />
    </div>
  )
}
