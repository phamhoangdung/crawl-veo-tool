import { createFileRoute } from '@tanstack/react-router'
import { Library } from '@/features/library'

export const Route = createFileRoute('/_authenticated/library/')({
  component: Library,
})
