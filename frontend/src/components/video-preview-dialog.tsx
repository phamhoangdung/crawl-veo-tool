import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { FEATURE_CHANNEL_VIDEOS } from '@/config/app'
import {
  Download,
  ExternalLink,
  Loader2,
  UserCheck,
  UserPlus,
} from 'lucide-react'
import {
  getChannelVideos,
  getRelatedVideos,
  type TrendingVideo,
} from '@/lib/api'
import { useChannelFollow } from '@/hooks/use-channel-follow'
import { useVideoTaskProgress } from '@/hooks/use-task-progress'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { CoverImage } from '@/components/cover-image'

/** 1 small card in the horizontal suggestion strip — click to change the video being watched RIGHT INSIDE
 * the open dialog, without opening a dialog over a dialog (keeping the user in the continuous
 * discovery flow, see docs/phases/phase-22-channel-follow.md). */
function SuggestionCard({
  video,
  onSelect,
}: {
  video: TrendingVideo
  onSelect: () => void
}) {
  return (
    <button
      type='button'
      onClick={onSelect}
      className='w-32 shrink-0 text-left'
      title={video.title}
    >
      <CoverImage src={video.cover_url} className='w-full rounded-md' />
      <p className='mt-1 line-clamp-2 text-xs'>{video.title}</p>
    </button>
  )
}

function SuggestionRow({
  title,
  isLoading,
  videos,
  emptyMessage,
  onSelect,
}: {
  title: string
  isLoading: boolean
  videos: TrendingVideo[]
  emptyMessage?: string
  onSelect: (video: TrendingVideo) => void
}) {
  return (
    <div className='space-y-2'>
      <p className='text-xs font-medium text-muted-foreground'>{title}</p>
      {isLoading ? (
        <div className='flex gap-2 overflow-hidden'>
          {Array.from({ length: 4 }, (_, i) => (
            <div
              key={i}
              className='h-20 w-32 shrink-0 animate-pulse rounded-md bg-muted'
            />
          ))}
        </div>
      ) : videos.length === 0 ? (
        emptyMessage && (
          <p className='text-xs text-muted-foreground'>{emptyMessage}</p>
        )
      ) : (
        <div className='flex gap-2 overflow-x-auto pb-1'>
          {videos.map((v) => (
            <SuggestionCard
              key={v.bvid}
              video={v}
              onSelect={() => onSelect(v)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Popup for quickly viewing 1 video through the official embedded iframe (it does not fetch/decode
 * the video stream on the client itself) — shared by the Bilibili and YouTube video grids on the
 * Discovery screen, previously each wrote the same thing again (only the URL/label differed).
 *
 * Phase 22: when there is a `bvid` (Bilibili only — YouTube does not pass it, keeping the
 * old behavior) it adds a channel name block + follow button, and 2 horizontal suggestion strips lazy-fetched
 * ("Similar videos"/"Other videos in the channel"). The "other in the channel" strip can
 * degrade (`degraded`) due to Bilibili risk control — showing the proper message instead of a
 * silently empty list.
 *
 * User feedback: after watching in the popup, wanting to download meant closing the popup and
 * finding the exact card in the grid again (sometimes scrolled away) before clicking download — too
 * roundabout. Added a "Download video" button right in the popup (`onDownload`), syncing the %
 * over SSE exactly like the card in the grid if `videoId` already exists.
 */
export function VideoPreviewDialog({
  title,
  embedUrl,
  externalUrl,
  externalLabel,
  onClose,
  bvid = null,
  channelId = null,
  channelName = null,
  channelIsFollowed = false,
  onSelectVideo,
  channelVideosEnabled = FEATURE_CHANNEL_VIDEOS,
  videoId = null,
  onDownload,
  isDownloading = false,
}: {
  /** `null` = close the popup. */
  title: string | null
  embedUrl: string | null
  externalUrl: string | null
  externalLabel: string
  onClose: () => void
  bvid?: string | null
  channelId?: string | null
  channelName?: string | null
  channelIsFollowed?: boolean
  /** Clicking a suggestion card — the parent only needs to change the state of the video being watched. */
  onSelectVideo?: (video: TrendingVideo) => void
  /** Turn on the "Other videos in the channel" strip — defaults to `FEATURE_CHANNEL_VIDEOS`. */
  channelVideosEnabled?: boolean
  /** Real id in the DB of the video BEING WATCHED — `null` = never downloaded. When it has a value
   * it shows the %/"My videos" link instead of the download button (see `VideoCard`, same
   * pattern). Not passed (YouTube) = no download block shown in the popup. */
  videoId?: number | null
  onDownload?: () => void
  isDownloading?: boolean
}) {
  const open = title !== null
  const follow = useChannelFollow('bilibili')
  const task = useVideoTaskProgress(videoId ?? -1, 'download')

  const related = useQuery({
    queryKey: ['trending', 'bilibili', 'related', bvid],
    queryFn: () => getRelatedVideos(bvid!),
    enabled: open && bvid !== null,
    staleTime: 5 * 60 * 1000,
  })

  const channelVideos = useQuery({
    queryKey: ['trending', 'bilibili', 'channel-videos', channelId],
    queryFn: () => getChannelVideos(channelId!),
    enabled: open && channelId !== null && channelVideosEnabled,
    staleTime: 5 * 60 * 1000,
  })

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      {/* Limited by screen height + scrollable: a popup taller than the screen pushes the Close button/title out and out of reach. */}
      <DialogContent className='max-h-[92vh] gap-3 overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle className='line-clamp-2 pr-6'>{title}</DialogTitle>
        </DialogHeader>
        {embedUrl && externalUrl && (
          <div className='min-w-0 space-y-3'>
            {/* Max width by the 16:9 of 50% of the screen height — the video never takes up the whole screen. */}
            <div className='mx-auto aspect-video w-full max-w-[calc(50vh*16/9)] overflow-hidden rounded-md bg-black'>
              <iframe
                src={embedUrl}
                className='h-full w-full'
                allowFullScreen
                title={title ?? ''}
              />
            </div>

            <div className='flex flex-wrap items-center gap-2'>
              <Button asChild variant='outline' size='sm' className='w-fit'>
                <a href={externalUrl} target='_blank' rel='noopener noreferrer'>
                  <ExternalLink className='size-4' />
                  {externalLabel}
                </a>
              </Button>

              {onDownload &&
                (videoId === null ? (
                  <Button
                    size='sm'
                    disabled={isDownloading}
                    onClick={onDownload}
                  >
                    {isDownloading ? (
                      <Loader2 className='size-3.5 animate-spin' />
                    ) : (
                      <Download className='size-3.5' />
                    )}
                    Tải video
                  </Button>
                ) : task?.is_running ? (
                  <span className='text-sm text-muted-foreground tabular-nums'>
                    {task.stage_label} · {Math.round(task.percent)}%
                  </span>
                ) : (
                  <Button asChild size='sm' variant='secondary'>
                    <Link
                      to='/videos/$videoId'
                      params={{ videoId: String(videoId) }}
                    >
                      Đã có trong thư viện → Video của tôi
                    </Link>
                  </Button>
                ))}

              {bvid && channelId && channelName && (
                <>
                  <span className='text-sm text-muted-foreground'>
                    {channelName}
                  </span>
                  <Button
                    size='sm'
                    variant={channelIsFollowed ? 'secondary' : 'outline'}
                    disabled={follow.isPending}
                    onClick={() =>
                      follow.mutate({
                        channelId,
                        name: channelName,
                        followed: !channelIsFollowed,
                      })
                    }
                  >
                    {follow.isPending ? (
                      <Loader2 className='size-3.5 animate-spin' />
                    ) : channelIsFollowed ? (
                      <UserCheck className='size-3.5' />
                    ) : (
                      <UserPlus className='size-3.5' />
                    )}
                    {channelIsFollowed ? 'Đang theo dõi' : 'Theo dõi'}
                  </Button>
                </>
              )}
            </div>

            {bvid && onSelectVideo && (
              <div className='space-y-3'>
                <SuggestionRow
                  title='Video tương tự'
                  isLoading={related.isLoading}
                  videos={related.data?.videos ?? []}
                  onSelect={onSelectVideo}
                />
                {channelVideosEnabled && (
                  <SuggestionRow
                    title='Video khác trong kênh'
                    isLoading={channelVideos.isLoading}
                    videos={channelVideos.data?.videos ?? []}
                    emptyMessage={
                      channelVideos.data?.degraded
                        ? 'Bilibili đang giới hạn truy cập kênh này, thử lại sau.'
                        : 'Chưa có video nào khác.'
                    }
                    onSelect={onSelectVideo}
                  />
                )}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
