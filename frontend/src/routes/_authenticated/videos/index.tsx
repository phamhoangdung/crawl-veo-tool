import { createFileRoute } from '@tanstack/react-router'
import { Videos } from '@/features/videos'

export const Route = createFileRoute('/_authenticated/videos/')({
  component: Videos,
})
