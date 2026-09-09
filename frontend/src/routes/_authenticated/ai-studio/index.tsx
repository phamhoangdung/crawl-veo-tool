import { createFileRoute } from '@tanstack/react-router'
import { AiStudio } from '@/features/ai-studio'

export const Route = createFileRoute('/_authenticated/ai-studio/')({
  component: AiStudio,
})
