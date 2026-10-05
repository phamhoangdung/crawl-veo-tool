import { useMutation, useQueryClient } from '@tanstack/react-query'
import { setChannelFollowed } from '@/lib/api'

/**
 * Toggle following 1 channel — Phase 22. Wraps `setChannelFollowed` with a light
 * optimistic update (refreshing the `['channels', 'followed']` cache when done) so the
 * "Follow"/"Following" button in the preview popup responds right away, without
 * waiting for a round trip to see the state change.
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
