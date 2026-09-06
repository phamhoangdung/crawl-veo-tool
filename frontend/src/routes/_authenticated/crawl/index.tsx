import { createFileRoute } from '@tanstack/react-router'
import { Crawl } from '@/features/crawl'

export const Route = createFileRoute('/_authenticated/crawl/')({
  component: Crawl,
})
