import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@/styles/index.css'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { api, getFollowedCategories, getTrendingCategories } from '@/lib/api'
import { bootPercent, type BootStepId } from '@/lib/boot-steps'
import { BootGate } from './boot-gate'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn() },
  getTrendingCategories: vi.fn(),
  getFollowedCategories: vi.fn(),
}))
const mockHealth = vi.mocked(api.get)
const mockCategories = vi.mocked(getTrendingCategories)
const mockFollowed = vi.mocked(getFollowedCategories)

async function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const screen = await render(
    <QueryClientProvider client={client}>
      <BootGate>
        <p>APP-READY</p>
      </BootGate>
    </QueryClientProvider>
  )
  return { screen, client }
}

describe('bootPercent', () => {
  it('cộng đúng trọng số từng bước đã xong', () => {
    const p = (...ids: BootStepId[]) => bootPercent(new Set(ids))
    expect(p()).toBe(0)
    expect(p('backend')).toBe(60)
    expect(p('backend', 'categories')).toBe(80)
    expect(p('backend', 'categories', 'followed')).toBe(100)
  })
})

describe('BootGate', () => {
  beforeEach(() => {
    mockHealth.mockReset()
    mockCategories.mockReset()
    mockFollowed.mockReset()
  })

  it('che app cho tới khi backend + prefetch xong rồi mới hiện nội dung', async () => {
    mockHealth.mockResolvedValue({ data: { status: 'ok' } })
    mockCategories.mockResolvedValue([])
    mockFollowed.mockResolvedValue([])

    const { screen, client } = await mount()
    expect(screen.getByText('APP-READY').query()).toBeNull()

    await expect.element(screen.getByText('APP-READY')).toBeVisible()
    expect(mockHealth).toHaveBeenCalledWith('/health', expect.anything())
    // Cache đã được làm ấm để trang Khám phá không phải chờ lại.
    expect(client.getQueryData(['trending', 'bilibili', 'categories'])).toEqual(
      []
    )
    expect(client.getQueryData(['trending', 'bilibili', 'followed'])).toEqual(
      []
    )
  })

  it('đợi backend: health lỗi vài lần rồi mới thành công vẫn vào được app', async () => {
    mockHealth
      .mockRejectedValueOnce(new Error('ECONNREFUSED'))
      .mockRejectedValueOnce(new Error('ECONNREFUSED'))
      .mockResolvedValue({ data: { status: 'ok' } })
    mockCategories.mockResolvedValue([])
    mockFollowed.mockResolvedValue([])

    const { screen } = await mount()
    await expect
      .element(screen.getByText('APP-READY'), { timeout: 8000 })
      .toBeVisible()
    expect(mockHealth).toHaveBeenCalledTimes(3)
  })

  it('prefetch lỗi không chặn app', async () => {
    mockHealth.mockResolvedValue({ data: { status: 'ok' } })
    mockCategories.mockRejectedValue(new Error('500'))
    mockFollowed.mockRejectedValue(new Error('500'))

    const { screen } = await mount()
    await expect.element(screen.getByText('APP-READY')).toBeVisible()
  })
})
