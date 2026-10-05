import { ConfigDrawer } from '@/components/config-drawer'
import { Search } from '@/components/search'
import { SystemLogsButton } from '@/components/system-logs-button'
import { TaskMonitor } from '@/components/task-monitor'
import { ThemeSwitch } from '@/components/theme-switch'
import { Header } from './header'

/**
 * The standard header bar used on EVERY page — previously each page copied this block
 * verbatim (10 files), leading to real drift: the Settings page lacked
 * `<TaskMonitor />` entirely because when this icon was added nobody remembered to edit all 10 places.
 */
export function AppHeader() {
  return (
    <Header>
      <Search />
      <div className='ms-auto flex items-center space-x-4'>
        <TaskMonitor />
        <ThemeSwitch />
        <ConfigDrawer />
        <SystemLogsButton />
      </div>
    </Header>
  )
}
