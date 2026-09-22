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
  UserCog,
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
      // Nhóm theo luồng làm việc thật: tìm video → xử lý → lấy kết quả.
      title: 'Nội dung',
      items: [
        {
          title: 'Tổng quan',
          url: '/',
          icon: LayoutDashboard,
        },
        {
          // Phase 20: gộp "Xu hướng" + "Tìm & tải" — trước đây tách 2 trang
          // khiến tick chọn ở Trending rồi "thêm vào hàng đợi" ở Crawl không
          // còn màn hình nào hiển thị lại được (xem
          // docs/phases/phase-20-discovery-workspace.md).
          title: 'Khám phá video',
          url: '/discover',
          icon: TrendingUp,
        },
        {
          // Trước đây "Chủ đề quan tâm" + biểu đồ chuyên mục (bên trong trang
          // Xu hướng cũ) tách rời — giờ gộp thành 2 tab của 1 trang báo cáo.
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
