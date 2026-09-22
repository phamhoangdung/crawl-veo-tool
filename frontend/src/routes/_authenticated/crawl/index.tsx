import { createFileRoute, redirect } from '@tanstack/react-router'

// Phase 20: gộp "Xu hướng" + "Tìm & tải" thành 1 màn Khám phá — giữ route cũ
// làm redirect để link/bookmark cũ không vỡ, xem
// docs/phases/phase-20-discovery-workspace.md.
export const Route = createFileRoute('/_authenticated/crawl/')({
  beforeLoad: () => {
    throw redirect({ to: '/discover' })
  },
})
