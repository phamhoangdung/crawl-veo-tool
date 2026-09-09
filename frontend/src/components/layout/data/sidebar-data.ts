import {
  LayoutDashboard,
  Monitor,
  Clapperboard,
  Download,
  HelpCircle,
  KeyRound,
  LibraryBig,
  Palette,
  Settings,
  Sparkles,
  UserCog,
  TrendingUp,
  Workflow,
} from 'lucide-react'
import { APP_OWNER } from '@/config/app'
import { type SidebarData } from '../types'

export const sidebarData: SidebarData = {
  user: {
    name: APP_OWNER.name,
    email: APP_OWNER.email,
    avatar: '',
  },
  navGroups: [
    {
      // Nhóm theo luồng làm việc thật: tìm video → xử lý → lấy kết quả.
      title: 'Nội dung',
      items: [
        {
          title: 'Tổng quan',
          url: '/',
          icon: LayoutDashboard,
        },
        {
          title: 'Xu hướng',
          url: '/trending',
          icon: TrendingUp,
        },
        {
          title: 'Tìm & tải',
          url: '/crawl',
          icon: Download,
        },
        {
          title: 'Video của tôi',
          url: '/videos',
          icon: Clapperboard,
        },
        {
          title: 'AI Studio',
          url: '/ai-studio',
          icon: Sparkles,
        },
        {
          title: 'Dự án video',
          url: '/projects',
          icon: Workflow,
        },
        {
          title: 'Thư viện',
          url: '/library',
          icon: LibraryBig,
        },
      ],
    },
    {
      title: 'Hệ thống',
      items: [
        {
          title: 'API Keys',
          url: '/api-keys',
          icon: KeyRound,
        },
        {
          title: 'Cài đặt',
          icon: Settings,
          items: [
            {
              title: 'Tài khoản',
              url: '/settings/account',
              icon: UserCog,
            },
            {
              title: 'Giao diện',
              url: '/settings/appearance',
              icon: Palette,
            },
            {
              title: 'Hiển thị',
              url: '/settings/display',
              icon: Monitor,
            },
          ],
        },
        {
          title: 'Trợ giúp',
          url: '/help-center',
          icon: HelpCircle,
        },
      ],
    },
  ],
}
