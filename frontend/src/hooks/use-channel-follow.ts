import { useMutation, useQueryClient } from '@tanstack/react-query'
import { setChannelFollowed } from '@/lib/api'

/**
 * Toggle theo dõi 1 kênh — Phase 22. Bọc `setChannelFollowed` với cập nhật
 * optimistic nhẹ (làm mới cache `['channels', 'followed']` sau khi xong) để
 * nút "Theo dõi"/"Đang theo dõi" trong popup xem trước phản hồi ngay, không
 * phải đợi round-trip mới thấy đổi trạng thái.
 */
export function useChannelFollow(platform: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      channelId,
      name,
      followed,
    }: {
      channelId: string
      name: string
      followed: boolean
    }) => setChannelFollowed(platform, channelId, name, followed),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['channels', 'followed', platform] })
    },
  })
}
