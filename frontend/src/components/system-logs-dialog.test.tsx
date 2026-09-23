import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@/styles/index.css'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { getSystemLogs } from '@/lib/api'
import { SystemLogsDialog } from './system-logs-dialog'

vi.mock('@/lib/api', () => ({ getSystemLogs: vi.fn() }))
const mockLogs = vi.mocked(getSystemLogs)

async function mount(open: boolean) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return await render(
    <QueryClientProvider client={client}>
      <SystemLogsDialog open={open} onOpenChange={() => {}} />
    </QueryClientProvider>
  )
}

describe('SystemLogsDialog', () => {
  beforeEach(() => mockLogs.mockReset())

  it('không gọi API khi dialog đóng', async () => {
    await mount(false)
    await new Promise((r) => setTimeout(r, 100))
    expect(mockLogs).not.toHaveBeenCalled()
  })

  it('mở ra thì hiện đường dẫn file và các dòng nhật ký', async () => {
    mockLogs.mockResolvedValue({
      path: '/data/logs/backend.log',
      exists: true,
      lines: ['INFO đang chạy', 'ERROR có lỗi'],
    })
    const screen = await mount(true)
    await expect
      .element(screen.getByText('/data/logs/backend.log'))
      .toBeVisible()
    await expect.element(screen.getByText(/ERROR có lỗi/)).toBeVisible()
  })

  it('chưa có file nhật ký thì báo rõ thay vì để trống', async () => {
    mockLogs.mockResolvedValue({ path: 'p', exists: false, lines: [] })
    const screen = await mount(true)
    await expect.element(screen.getByText('Chưa có nhật ký nào.')).toBeVisible()
  })
})
