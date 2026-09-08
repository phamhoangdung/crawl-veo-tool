import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from 'vitest-browser-react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import '@/styles/index.css'
import { translateText } from '@/lib/api'
import { TranslatedTitle } from './translated-title'

// ESM không cho spy vào export trong browser mode — phải mock ở tầng module.
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

    // Mở trang là dịch sẵn 40 tiêu đề thì đốt quota cho dòng không ai xem.
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

    // Danh sách video re-up rất hay trùng tiêu đề — queryKey theo nội dung nên
    // cả hai dòng dùng chung 1 kết quả.
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
    // Trả về undefined thay vì throw: vitest browser mode coi MỌI lỗi ném ra
    // trong trang là test đỏ, kể cả lỗi đã được TanStack Query xử lý. Đây vẫn
    // đi đúng nhánh "không có data" mà người dùng gặp khi hết quota.
    mockTranslate.mockResolvedValue(undefined as never)
    const screen = await wrap(<TranslatedTitle title={ZH} />)
    await screen.getByText(ZH).first().hover()
    await new Promise((r) => setTimeout(r, 150))

    // Không hiện bản dịch rác, và nguyên văn vẫn còn để người dùng tự đọc.
    await expect.element(screen.getByText(ZH).first()).toBeInTheDocument()
  })
})
