import { createFileRoute, redirect } from '@tanstack/react-router'

// The template's Profile page is temporarily hidden along with the account entries — going to /settings
// redirects straight to the first real settings page.
export const Route = createFileRoute('/_authenticated/settings/')({
  beforeLoad: () => {
    throw redirect({ to: '/settings/downloads' })
  },
})
