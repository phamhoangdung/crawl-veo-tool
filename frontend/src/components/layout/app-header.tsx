import { ConfigDrawer } from '@/components/config-drawer'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { TaskMonitor } from '@/components/task-monitor'
import { ThemeSwitch } from '@/components/theme-switch'
import { Header } from './header'

/**
 * Thanh header chuẩn dùng ở MỌI trang — trước đây mỗi trang tự chép lại y hệt
 * khối này (10 file), dẫn tới lệch thật: trang Settings thiếu hẳn
 * `<TaskMonitor />` vì lúc thêm icon này không ai nhớ sửa cả 10 nơi.
 */
export function AppHeader() {
  return (
    <Header>
      <Search />
      <div className='ms-auto flex items-center space-x-4'>
        <TaskMonitor />
        <ThemeSwitch />
        <ConfigDrawer />
        <ProfileDropdown />
      </div>
    </Header>
  )
}
