import { createFileRoute, redirect } from '@tanstack/react-router'

// Phase 20: merged "Trends" + "Find & download" into 1 Discovery screen — keep the old route
// as a redirect so old links/bookmarks do not break, see
// docs/phases/phase-20-discovery-workspace.md.
export const Route = createFileRoute('/_authenticated/crawl/')({
  beforeLoad: () => {
    throw redirect({ to: '/discover' })
  },
})
