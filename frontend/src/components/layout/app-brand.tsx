import { Link } from '@tanstack/react-router'
import { Logo } from '@/assets/logo'
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'
import { APP_NAME, APP_TAGLINE } from '@/config/app'

/**
 * The software name at the top of the sidebar. Replaces the template's TeamSwitcher — the tool runs
 * locally for one user so there is no notion of switching teams.
 */
export function AppBrand() {
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton size='lg' asChild>
          <Link to='/'>
            <div className='flex aspect-square size-8 items-center justify-center'>
              <Logo className='size-8' />
            </div>
            <div className='grid flex-1 text-start text-sm leading-tight'>
              <span className='truncate font-semibold'>{APP_NAME}</span>
              <span className='truncate text-xs text-muted-foreground'>
                {APP_TAGLINE}
              </span>
            </div>
          </Link>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
