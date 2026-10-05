import { createFileRoute, redirect } from '@tanstack/react-router'

// Phase 20: "Topics of interest" merged into 1 tab of the Trend report page —
// keep the old route as a redirect so old links/bookmarks do not break, see
// docs/phases/phase-20-discovery-workspace.md.
export const Route = createFileRoute('/_authenticated/topics/')({
  beforeLoad: () => {
    throw redirect({ to: '/insights' })
  },
})
