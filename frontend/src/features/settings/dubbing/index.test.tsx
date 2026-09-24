import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from 'vitest-browser-react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import '@/styles/index.css'
import { getAppSettings, updateAppSettings } from '@/lib/api'
import { SettingsDubbing } from './index'

vi.mock('@/lib/api', () => ({
  getAppSettings: vi.fn(),
  updateAppSettings: vi.fn(),
  getApiErrorMessage: (_: unknown, fallback: string) => fallback,
}))
const mockGet = vi.mocked(getAppSettings)
const mockUpdate = vi.mocked(updateAppSettings)

const BASE = { download_connections: 1, download_max_videos: 3 }

async function wrap() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return await render(
    <QueryClientProvider client={client}>
      <SettingsDubbing />
    </QueryClientProvider>
  )
}

describe('SettingsDubbing — công tắc phân vai người nói', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockUpdate.mockReset()
  })

  it('mặc định tắt', async () => {
    mockGet.mockResolvedValue({ ...BASE, speaker_diarization_enabled: false })
    const screen = await wrap()
    await expect
      .element(screen.getByRole('switch', { name: 'Bật phân vai người nói' }))
      .not.toBeChecked()
  })

  it('bật công tắc gửi đúng 1 trường lên backend', async () => {
    mockGet.mockResolvedValue({ ...BASE, speaker_diarization_enabled: false })
    mockUpdate.mockResolvedValue({ ...BASE, speaker_diarization_enabled: true })
    const screen = await wrap()

    await screen.getByRole('switch', { name: 'Bật phân vai người nói' }).click()

    // React Query gọi mutationFn(variables, context) — chỉ so tham số đầu.
    await vi.waitFor(() => expect(mockUpdate).toHaveBeenCalled())
    expect(mockUpdate.mock.calls[0][0]).toEqual({
      speaker_diarization_enabled: true,
    })
  })
})
