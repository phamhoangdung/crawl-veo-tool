import { createFileRoute, redirect } from '@tanstack/react-router'

// Trang Profile của template tạm ẩn cùng các mục tài khoản — vào /settings thì
// chuyển thẳng tới trang cài đặt thật đầu tiên.
export const Route = createFileRoute('/_authenticated/settings/')({
  beforeLoad: () => {
    throw redirect({ to: '/settings/downloads' })
  },
})
