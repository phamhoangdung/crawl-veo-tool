import { createFileRoute } from '@tanstack/react-router'
import { Insights } from '@/features/insights'

export const Route = createFileRoute('/_authenticated/insights/')({
  component: Insights,
})
