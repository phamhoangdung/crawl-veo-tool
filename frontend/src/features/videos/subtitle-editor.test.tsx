import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from 'vitest-browser-react'
import '@/styles/index.css'
import { describe, expect, it, vi } from 'vitest'
import type { TranscriptSegment } from '@/lib/api'
import { SubtitleEditor } from './subtitle-editor'

function makeSegments(count: number): TranscriptSegment[] {
  return Array.from({ length: count }, (_, i) => ({
    start: i * 5,
    end: i * 5 + 4,
    text: `第${i}句`,
    translated_text: `Câu ${i}`,
    speaker: '',
  }))
}

async function renderEditor(count: number) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const segments = makeSegments(count)
  const screen = await render(
    <QueryClientProvider client={client}>
      <SubtitleEditor
        videoId={1}
        title='Video test'
        segments={segments}
        availableVariants={{ burned: false, dubbed: false, original: false }}
        open
        onOpenChange={() => {}}
      />
    </QueryClientProvider>
  )
  // Virtualizer đo container qua ResizeObserver (bất đồng bộ) — chờ tới khi
  // nó thật sự dựng xong ít nhất 1 hàng thay vì đoán 1 khoảng chờ cố định.
  await vi.waitFor(() => {
    expect(document.querySelectorAll('textarea').length).toBeGreaterThan(0)
  })
  return screen
}

describe('SubtitleEditor — ảo hoá danh sách', () => {
  it('danh sách lớn không dựng hết mọi hàng thành DOM node', async () => {
    await renderEditor(300)

    const textareas = document.querySelectorAll('textarea')
    // 300 câu x 2 textarea/câu = 600 nếu KHÔNG ảo hoá — kiểm tra ít hơn hẳn.
    expect(textareas.length).toBeGreaterThan(0)
    expect(textareas.length).toBeLessThan(200)
  })

  it('sửa 1 câu không đổi nội dung câu khác', async () => {
    const screen = await renderEditor(30)

    const firstText = document.querySelectorAll('textarea')[0] as HTMLTextAreaElement
    await screen
      .getByPlaceholder('Lời thoại gốc')
      .first()
      .fill('Đã sửa câu đầu')

    expect(firstText.value).toBe('Đã sửa câu đầu')

    // Câu thứ 2 (textarea gốc thứ 3, vì mỗi câu có 2 textarea) phải còn nguyên.
    const secondText = document.querySelectorAll('textarea')[2] as HTMLTextAreaElement
    expect(secondText.value).toBe('第1句')
  })

  it('hiện đúng tổng số câu dù chưa dựng hết DOM', async () => {
    const screen = await renderEditor(300)
    await expect.element(screen.getByText('300 câu')).toBeInTheDocument()
  })
})
