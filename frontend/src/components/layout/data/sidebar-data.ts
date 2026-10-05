import {
  LayoutDashboard,
  Monitor,
  Clapperboard,
  HelpCircle,
  KeyRound,
  LibraryBig,
  Palette,
  Settings,
  Sparkles,
  TrendingUp,
  BarChart3,
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
      // Grouped by the real workflow: find videos → process → get the result.
      title: 'Nội dung',
      items: [
        {
          title: 'Tổng quan',
          url: '/',
          icon: LayoutDashboard,
        },
        {
          // Phase 20: merged "Trends" + "Find & download" — previously 2 separate pages
          // meant ticking in Trending then "adding to the queue" in Crawl had
          // no screen left that could show it again (see
          // docs/phases/phase-20-discovery-workspace.md).
          title: 'Khám phá video',
          url: '/discover',
          icon: TrendingUp,
        },
        {
          // Previously "Topics of interest" + the category chart (inside the old
          // Trends page) were separate — now merged into 2 tabs of 1 report page.
          title: 'Báo cáo xu hướng',
          url: '/insights',
          icon: BarChart3,
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
