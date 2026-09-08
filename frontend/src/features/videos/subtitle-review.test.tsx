import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from 'vitest-browser-react'
import '@/styles/index.css'
import { describe, expect, it } from 'vitest'
import type { TranscriptSegment } from '@/lib/api'
import { SubtitleReview } from './subtitle-review'

const segments: TranscriptSegment[] = Array.from({ length: 32 }, (_, i) => ({
  start: i * 5,
  end: i * 5 + 4,
  text: `第${i}句中文字幕`,
  translated_text: `Câu phụ đề tiếng Việt số ${i}`,
}))

async function renderReview() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return await render(
    <QueryClientProvider client={client}>
      <SubtitleReview
        videoId={1}
        segments={segments}
        hasTranslation
        variant='dubbed'
        onEdit={() => {}}
      />
    </QueryClientProvider>
  )
}

describe('SubtitleReview — kích thước hiển thị', () => {
  it('khung video bị khoá chiều cao, không nở theo tỉ lệ dọc 9:16', async () => {
    await renderReview()
    const video = document.querySelector('video')!
    await new Promise((r) => setTimeout(r, 50))

    // Thẻ <video> trong test không có file thật nên không tự cao theo tỉ lệ;
    // kiểm tra chính cái chặn: phải có max-height, nếu không video dọc sẽ cao
    // gấp ~1.8 lần bề rộng cột và đẩy mọi thứ khác ra ngoài màn hình.
    const style = getComputedStyle(video)
    expect(style.maxHeight).not.toBe('none')
    expect(parseFloat(style.maxHeight)).toBeLessThanOrEqual(window.innerHeight * 0.62)
    // object-contain giữ tỉ lệ gốc thay vì bóp méo hình khi bị khoá chiều cao.
    expect(style.objectFit).toBe('contain')
  })

  it('danh sách phụ đề cuộn được và cao hơn khung cũ 28rem', async () => {
    await renderReview()
    const list = document.querySelector('ul')!
    await new Promise((r) => setTimeout(r, 50))

    const rect = list.getBoundingClientRect()
    // 28rem = 448px là giới hạn cứng cũ khiến danh sách chỉ hiện 1 khúc.
    expect(rect.height).toBeGreaterThan(448)
    // Khung phải cho phép cuộn khi nội dung dài hơn (cửa sổ test cao nên 32 câu
    // có thể vừa khít — kiểm tra thuộc tính cuộn thay vì ép phải tràn).
    expect(getComputedStyle(list).overflowY).toBe('auto')
  })

  it('trang không tràn ngang', async () => {
    await renderReview()
    await new Promise((r) => setTimeout(r, 50))

    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(
      document.documentElement.clientWidth + 1
    )
  })
})
