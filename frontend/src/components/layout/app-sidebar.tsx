import { useLayout } from '@/context/layout-provider'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
} from '@/components/ui/sidebar'
import { AppBrand } from './app-brand'
import { sidebarData } from './data/sidebar-data'
import { NavGroup } from './nav-group'
import { SidebarCredit } from './sidebar-credit'

export function AppSidebar() {
  const { collapsible, variant } = useLayout()
  return (
    <Sidebar collapsible={collapsible} variant={variant}>
      <SidebarHeader>
        <AppBrand />
      </SidebarHeader>
      <SidebarContent>
        {sidebarData.navGroups.map((props) => (
          <NavGroup key={props.title} {...props} />
        ))}
      </SidebarContent>
      <SidebarFooter>
        {/* The account block (NavUser) is temporarily hidden — a local single-user build. */}
        <SidebarCredit />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
