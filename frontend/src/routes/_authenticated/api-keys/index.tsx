import { createFileRoute } from '@tanstack/react-router'
import { ApiKeys } from '@/features/api-keys'

export const Route = createFileRoute('/_authenticated/api-keys/')({
  component: ApiKeys,
})
