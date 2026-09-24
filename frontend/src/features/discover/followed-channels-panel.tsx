import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FEATURE_CHANNEL_VIDEOS } from '@/config/app'
import { Loader2, Radio } from 'lucide-react'
import { getChannelVideos, getFollowedChannels } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { VideoGridPanel } from './video-grid-panel'

/**
 * Tab "Kênh đã theo dõi" ở màn Khám phá (Phase 22, quyết định đã chốt #2 —
 * 1 chip lọc trong hàng chip chuyên mục, không thêm mục điều hướng riêng để
 * không đi ngược hướng Phase 20 vừa gộp bớt điều hướng).
 *
 * v1 đơn giản: chọn 1 kênh tại 1 thời điểm rồi xem video của kênh đó — tái
 * dùng nguyên `VideoGridPanel` vì `getChannelVideos` đã trả đúng hình dạng
 * `TrendingPage`. Gộp nhiều kênh thành 1 feed chung để sau nếu cần (xem plan).
 */
export function FollowedChannelsPanel() {
  const [selectedChannelId, setSelectedChannelId] = useState<string | null>(
    null
  )

  const { data: channels, isLoading } = useQuery({
    queryKey: ['channels', 'followed', 'bilibili'],
    queryFn: () => getFollowedChannels('bilibili'),
  })

  if (isLoading) {
    return (
      <p className='flex items-center gap-2 text-muted-foreground'>
        <Loader2 className='size-4 animate-spin' />
        Đang tải...
      </p>
    )
  }

  if (!channels || channels.length === 0) {
    return (
      <p className='text-sm text-muted-foreground'>
        Chưa theo dõi kênh nào — bấm &quot;Theo dõi&quot; trong popup xem trước
        1 video để bắt đầu.
      </p>
    )
  }

  const selected = channels.find((c) => c.channel_id === selectedChannelId)

  return (
    <div className='space-y-4'>
      <div className='flex flex-wrap gap-2'>
        {channels.map((channel) => (
          <Button
            key={channel.channel_id}
            type='button'
            size='sm'
            variant={
              channel.channel_id === selectedChannelId ? 'default' : 'outline'
            }
            onClick={() => setSelectedChannelId(channel.channel_id)}
          >
            <Radio className='size-3.5' />
            {channel.name}
          </Button>
        ))}
      </div>

      {selected && !FEATURE_CHANNEL_VIDEOS ? (
        <p className='text-sm text-muted-foreground'>
          Xem video theo kênh đang tạm tắt (Bilibili chặn truy cập kênh). Kênh
          bạn theo dõi vẫn được lưu lại.
        </p>
      ) : selected ? (
        <VideoGridPanel
          queryKey={[
            'trending',
            'bilibili',
            'channel-page',
            selected.channel_id,
          ]}
          fetchPage={(page) => getChannelVideos(selected.channel_id, page)}
        />
      ) : (
        <p className='text-sm text-muted-foreground'>
          Chọn 1 kênh ở trên để xem video mới nhất.
        </p>
      )}
    </div>
  )
}
