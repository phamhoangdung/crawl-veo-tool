import { createFileRoute } from '@tanstack/react-router'
import { Topics } from '@/features/topics'

export const Route = createFileRoute('/_authenticated/topics/')({
  component: Topics,
})
