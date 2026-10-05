import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@/styles/index.css'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { getAppSettings, updateAppSettings } from '@/lib/api'
import { SettingsDownloads } from './index'

// ESM does not allow spying on exports in browser mode — must mock at the module level.
vi.mock('@/lib/api', () => ({
  getAppSettings: vi.fn(),
  updateAppSettings: vi.fn(),
  getApiErrorMessage: (_: unknown, fallback: string) => fallback,
}))
const mockGet = vi.mocked(getAppSettings)
const mockUpdate = vi.mocked(updateAppSettings)

async function wrap() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
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
    mockGet.mockResolvedValue({
      download_connections: 1,
      download_max_videos: 3,
      speaker_diarization_enabled: false,
    })

    const screen = await wrap()

    const connections = screen.getByLabelText('Số luồng mỗi video')
    const maxVideos = screen.getByLabelText('Số video tải cùng lúc')
    await expect.element(connections).toHaveValue('1')
    await expect.element(maxVideos).toHaveValue('3')
  })

  it('đổi số luồng gọi đúng API và không đụng vào số video tải cùng lúc', async () => {
    mockGet.mockResolvedValue({
      download_connections: 1,
      download_max_videos: 3,
      speaker_diarization_enabled: false,
    })
    mockUpdate.mockResolvedValue({
      download_connections: 8,
      download_max_videos: 3,
      speaker_diarization_enabled: false,
    })

    const screen = await wrap()

    await screen.getByLabelText('Số luồng mỗi video').selectOptions('8')

    // React Query calls `mutationFn(variables, context)` — only the first argument
    // (`variables`) is the real app data, the 2nd argument is TanStack internal.
    await vi.waitFor(() =>
      expect(mockUpdate.mock.calls[0]?.[0]).toEqual({ download_connections: 8 })
    )
    // Do not send download_max_videos along on its own — each box only edits its own setting.
    expect(mockUpdate).toHaveBeenCalledTimes(1)
  })

  it('lỗi lưu cài đặt thì không làm sập trang', async () => {
    mockGet.mockResolvedValue({
      download_connections: 1,
      download_max_videos: 3,
      speaker_diarization_enabled: false,
    })
    mockUpdate.mockRejectedValue(new Error('network error'))

    const screen = await wrap()

    await screen.getByLabelText('Số luồng mỗi video').selectOptions('4')

    await vi.waitFor(() => expect(mockUpdate).toHaveBeenCalled())
    // The page still shows content, no white-screen crash.
    await expect
      .element(screen.getByText('Số luồng mỗi video'))
      .toBeInTheDocument()
  })
})
