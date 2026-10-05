import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from 'vitest-browser-react'
import '@/styles/index.css'
import { describe, expect, it, vi } from 'vitest'
import type { TranscriptSegment } from '@/lib/api'
import { SubtitleReview } from './subtitle-review'

const segments: TranscriptSegment[] = Array.from({ length: 32 }, (_, i) => ({
  start: i * 5,
  end: i * 5 + 4,
  text: `第${i}句中文字幕`,
  translated_text: `Câu phụ đề tiếng Việt số ${i}`,
  speaker: '',
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

    // The <video> tag in the test has no real file so it does not size itself by ratio;
    // check the blocker itself: it must have a max-height, otherwise a vertical video would be
    // ~1.8 times the column width and push everything else off the screen.
    const style = getComputedStyle(video)
    expect(style.maxHeight).not.toBe('none')
    expect(parseFloat(style.maxHeight)).toBeLessThanOrEqual(window.innerHeight * 0.62)
    // object-contain keeps the original ratio instead of distorting the picture when the height is locked.
    expect(style.objectFit).toBe('contain')
  })

  it('danh sách phụ đề cuộn được và cao hơn khung cũ 28rem', async () => {
    await renderReview()
    const list = document.querySelector('ul')!
    await new Promise((r) => setTimeout(r, 50))

    const rect = list.getBoundingClientRect()
    // 28rem = 448px was the old hard limit that made the list show only 1 slice.
    expect(rect.height).toBeGreaterThan(448)
    // The frame must allow scrolling when the content is longer (the test window is tall so 32 sentences
    // may fit exactly — check the scroll property instead of forcing an overflow).
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

describe('SubtitleReview — ảo hoá danh sách', () => {
  it('danh sách thật sự render được câu (virtualizer đo đúng container)', async () => {
    await renderReview()
    // A trap met in SubtitleEditor: the virtualizer can measure 0 rows if the
    // container did not yet have its real size at the first measurement — confirm it does not
    // repeat here by waiting for real sentence content, not only checking the frame.
    await vi.waitFor(() => {
      expect(document.body.textContent).toContain('Câu phụ đề tiếng Việt số 0')
    })
  })

  it('danh sách lớn không dựng hết mọi hàng thành DOM node', async () => {
    // 32 sentences (the standard fixture above) may fit a tall test window exactly — use
    // 400 sentences to be sure overscan cannot cover the whole list.
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const manySegments: TranscriptSegment[] = Array.from({ length: 400 }, (_, i) => ({
      start: i * 5,
      end: i * 5 + 4,
      text: `第${i}句`,
      translated_text: `Câu ${i}`,
      speaker: '',
    }))
    await render(
      <QueryClientProvider client={client}>
        <SubtitleReview
          videoId={1}
          segments={manySegments}
          hasTranslation
          variant='dubbed'
          onEdit={() => {}}
        />
      </QueryClientProvider>
    )

    await vi.waitFor(() => {
      expect(document.querySelectorAll('ul li').length).toBeGreaterThan(0)
    })
    expect(document.querySelectorAll('ul li').length).toBeLessThan(400)
  })
})
