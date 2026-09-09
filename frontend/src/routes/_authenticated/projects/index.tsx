import { createFileRoute } from '@tanstack/react-router'
import { ProjectFlow } from '@/features/flow'

export const Route = createFileRoute('/_authenticated/projects/')({
  component: ProjectFlow,
})
