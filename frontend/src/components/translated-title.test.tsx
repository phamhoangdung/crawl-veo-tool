import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from 'vitest-browser-react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import '@/styles/index.css'
import { translateText } from '@/lib/api'
import { TranslatedTitle } from './translated-title'

// ESM does not allow spying on exports in browser mode — must mock at the module level.
vi.mock('@/lib/api', () => ({ translateText: vi.fn() }))
const mockTranslate = vi.mocked(translateText)

const ZH = '一看就懂！最完整的匹克球规则'

async function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return await render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe('TranslatedTitle', () => {
  beforeEach(() => mockTranslate.mockReset())

  it('KHÔNG gọi API dịch khi chưa hover', async () => {
    await wrap(<TranslatedTitle title={ZH} />)
    await new Promise((r) => setTimeout(r, 100))

    // Opening the page and pre-translating 40 titles burns quota on rows nobody looks at.
    expect(mockTranslate).not.toHaveBeenCalled()
  })

  it('gọi API và hiện bản dịch khi hover', async () => {
    mockTranslate.mockResolvedValue({
      translated_text: 'Luật pickleball đầy đủ nhất',
      cached: false,
    })

    const screen = await wrap(<TranslatedTitle title={ZH} />)
    await screen.getByText(ZH).first().hover()

    await vi.waitFor(() => expect(mockTranslate).toHaveBeenCalledWith(ZH))
    await expect
      .element(screen.getByText('Luật pickleball đầy đủ nhất').first())
      .toBeInTheDocument()
  })

  it('hai tiêu đề GIỐNG nhau chỉ dịch 1 lần', async () => {
    mockTranslate.mockResolvedValue({ translated_text: 'Bản dịch', cached: true })

    const screen = await wrap(
      <div>
        <TranslatedTitle title={ZH} className='a' />
        <TranslatedTitle title={ZH} className='b' />
      </div>
    )

    // A list of re-uploaded videos very often has duplicate titles — the queryKey is by content so
    // both rows share 1 result.
    await screen.getByText(ZH).first().hover()
    await vi.waitFor(() => expect(mockTranslate).toHaveBeenCalledTimes(1))

    await screen.getByText(ZH).last().hover()
    await new Promise((r) => setTimeout(r, 200))

    expect(mockTranslate).toHaveBeenCalledTimes(1)
  })

  it('tiêu đề không có chữ Hán thì không gọi API dịch', async () => {
    const screen = await wrap(<TranslatedTitle title='Pickleball rules explained' />)
    await screen.getByText('Pickleball rules explained').first().hover()
    await new Promise((r) => setTimeout(r, 150))

    expect(mockTranslate).not.toHaveBeenCalled()
  })

  it('báo lỗi rõ khi dịch thất bại', async () => {
    // Return undefined instead of throwing: vitest browser mode treats EVERY error thrown
    // in the page as a failed test, even errors already handled by TanStack Query. This still
    // goes through the "no data" branch the user meets when out of quota.
    mockTranslate.mockResolvedValue(undefined as never)
    const screen = await wrap(<TranslatedTitle title={ZH} />)
    await screen.getByText(ZH).first().hover()
    await new Promise((r) => setTimeout(r, 150))

    // Do not show garbage translation, and the original remains for the user to read.
    await expect.element(screen.getByText(ZH).first()).toBeInTheDocument()
  })
})
