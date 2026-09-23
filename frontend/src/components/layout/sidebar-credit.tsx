import { APP_CREDIT } from '@/config/app'

export function SidebarCredit() {
  return (
    <p className='px-2 py-1 text-center text-xs text-muted-foreground group-data-[collapsible=icon]:hidden'>
      Powered by{' '}
      <span className='font-semibold text-foreground'>{APP_CREDIT}</span>
    </p>
  )
}
