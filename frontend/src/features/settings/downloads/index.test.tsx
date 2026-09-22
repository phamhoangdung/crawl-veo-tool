import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from 'vitest-browser-react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import '@/styles/index.css'
import { getAppSettings, updateAppSettings } from '@/lib/api'
import { SettingsDownloads } from './index'

// ESM không cho spy vào export trong browser mode — phải mock ở tầng module.
vi.mock('@/lib/api', () => ({
  getAppSettings: vi.fn(),
  updateAppSettings: vi.fn(),
  getApiErrorMessage: (_: unknown, fallback: string) => fallback,
}))
const mockGet = vi.mocked(getAppSettings)
const mockUpdate = vi.mocked(updateAppSettings)

async function wrap() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return await render(
    <QueryClientProvider client={client}>
      <SettingsDownloads />
    </QueryClientProvider>
  )
}

describe('SettingsDownloads — Phase 21', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockUpdate.mockReset()
  })

  it('hiện đúng giá trị mặc định (1 luồng) khi vừa cài mới', async () => {
    mockGet.mockResolvedValue({ download_connections: 1, download_max_videos: 3 })

    const screen = await wrap()

    const connections = screen.getByLabelText('Số luồng mỗi video')
    const maxVideos = screen.getByLabelText('Số video tải cùng lúc')
    await expect.element(connections).toHaveValue('1')
    await expect.element(maxVideos).toHaveValue('3')
  })

  it('đổi số luồng gọi đúng API và không đụng vào số video tải cùng lúc', async () => {
    mockGet.mockResolvedValue({ download_connections: 1, download_max_videos: 3 })
    mockUpdate.mockResolvedValue({ download_connections: 8, download_max_videos: 3 })

    const screen = await wrap()

    await screen.getByLabelText('Số luồng mỗi video').selectOptions('8')

    // React Query gọi `mutationFn(variables, context)` — chỉ cần đúng đối số
    // đầu tiên (`variables`) là dữ liệu thật của app, đối số 2 là nội bộ TanStack.
    await vi.waitFor(() =>
      expect(mockUpdate.mock.calls[0]?.[0]).toEqual({ download_connections: 8 })
    )
    // Không tự ý gửi kèm download_max_videos — mỗi ô chỉ sửa đúng cài đặt của nó.
    expect(mockUpdate).toHaveBeenCalledTimes(1)
  })

  it('lỗi lưu cài đặt thì không làm sập trang', async () => {
    mockGet.mockResolvedValue({ download_connections: 1, download_max_videos: 3 })
    mockUpdate.mockRejectedValue(new Error('network error'))

    const screen = await wrap()

    await screen.getByLabelText('Số luồng mỗi video').selectOptions('4')

    await vi.waitFor(() => expect(mockUpdate).toHaveBeenCalled())
    // Trang vẫn còn hiện nội dung, không crash trắng trang.
    await expect.element(screen.getByText('Số luồng mỗi video')).toBeInTheDocument()
  })
})
