import { createFileRoute, redirect } from '@tanstack/react-router'

// Phase 20: "Chủ đề quan tâm" gộp thành 1 tab trong trang Báo cáo xu hướng —
// giữ route cũ làm redirect để link/bookmark cũ không vỡ, xem
// docs/phases/phase-20-discovery-workspace.md.
export const Route = createFileRoute('/_authenticated/topics/')({
  beforeLoad: () => {
    throw redirect({ to: '/insights' })
  },
})
