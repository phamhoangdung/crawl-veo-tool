import { useQuery } from '@tanstack/react-query'
import { ExternalLink, Loader2, UserCheck, UserPlus } from 'lucide-react'
import { getChannelVideos, getRelatedVideos, type TrendingVideo } from '@/lib/api'
import { useChannelFollow } from '@/hooks/use-channel-follow'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { CoverImage } from '@/components/cover-image'

/** 1 thẻ nhỏ trong dải gợi ý ngang — bấm để đổi video đang xem NGAY TRONG
 * dialog đang mở, không mở dialog chồng dialog (giữ người dùng ở lại luồng
 * khám phá liên tục, xem docs/phases/phase-22-channel-follow.md). */
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
      className='w-36 shrink-0 text-left'
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
            <div key={i} className='h-24 w-36 shrink-0 animate-pulse rounded-md bg-muted' />
          ))}
        </div>
      ) : videos.length === 0 ? (
        emptyMessage && <p className='text-xs text-muted-foreground'>{emptyMessage}</p>
      ) : (
        <div className='flex gap-2 overflow-x-auto pb-1'>
          {videos.map((v) => (
            <SuggestionCard key={v.bvid} video={v} onSelect={() => onSelect(v)} />
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Popup xem nhanh 1 video qua iframe nhúng chính thức (không tự lấy/giải mã
 * luồng video ở client) — dùng chung cho lưới video Bilibili và YouTube ở màn
 * Khám phá, trước đây mỗi bên tự viết lại y hệt (chỉ khác URL/nhãn).
 *
 * Phase 22: khi có `bvid` (chỉ Bilibili — YouTube không truyền, giữ nguyên
 * hành vi cũ) thêm khối tên kênh + nút theo dõi, và 2 dải gợi ý ngang lazy-fetch
 * ("Video tương tự"/"Video khác trong kênh"). Dải "khác trong kênh" có thể
 * suy giảm (`degraded`) do Bilibili risk-control — hiện đúng thông báo thay vì
 * danh sách rỗng im lặng.
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
}: {
  /** `null` = đóng popup. */
  title: string | null
  embedUrl: string | null
  externalUrl: string | null
  externalLabel: string
  onClose: () => void
  bvid?: string | null
  channelId?: string | null
  channelName?: string | null
  channelIsFollowed?: boolean
  /** Bấm vào 1 thẻ gợi ý — cha chỉ cần đổi state video đang xem. */
  onSelectVideo?: (video: TrendingVideo) => void
}) {
  const open = title !== null
  const follow = useChannelFollow('bilibili')

  const related = useQuery({
    queryKey: ['trending', 'bilibili', 'related', bvid],
    queryFn: () => getRelatedVideos(bvid!),
    enabled: open && bvid !== null,
    staleTime: 5 * 60 * 1000,
  })

  const channelVideos = useQuery({
    queryKey: ['trending', 'bilibili', 'channel-videos', channelId],
    queryFn: () => getChannelVideos(channelId!),
    enabled: open && channelId !== null,
    staleTime: 5 * 60 * 1000,
  })

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle className='line-clamp-2 pr-6'>{title}</DialogTitle>
        </DialogHeader>
        {embedUrl && externalUrl && (
          <div className='space-y-4'>
            <div className='aspect-video w-full overflow-hidden rounded-md bg-black'>
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

              {bvid && channelId && channelName && (
                <>
                  <span className='text-sm text-muted-foreground'>{channelName}</span>
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
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
