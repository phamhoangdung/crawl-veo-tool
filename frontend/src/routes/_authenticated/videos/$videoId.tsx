import { createFileRoute } from '@tanstack/react-router'
import { VideoDetail } from '@/features/videos/video-detail'

export const Route = createFileRoute('/_authenticated/videos/$videoId')({
  component: VideoDetail,
})
