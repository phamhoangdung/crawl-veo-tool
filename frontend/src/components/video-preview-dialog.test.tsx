import { render } from 'vitest-browser-react'
import '@/styles/index.css'
import { describe, expect, it, vi } from 'vitest'
import { VideoPreviewDialog } from './video-preview-dialog'

describe('VideoPreviewDialog', () => {
  it('đóng khi title=null — không hiện iframe/link', async () => {
    await render(
      <VideoPreviewDialog
        title={null}
        embedUrl={null}
        externalUrl={null}
        externalLabel='Mở trên Bilibili'
        onClose={() => {}}
      />
    )

    expect(document.querySelector('iframe')).toBeNull()
  })

  it('mở đúng iframe embed + link ngoài theo props truyền vào (dùng chung cho cả Bilibili lẫn YouTube)', async () => {
    await render(
      <VideoPreviewDialog
        title='Video test'
        embedUrl='https://player.bilibili.com/player.html?bvid=BV123'
        externalUrl='https://www.bilibili.com/video/BV123'
        externalLabel='Mở trên Bilibili'
        onClose={() => {}}
      />
    )

    const iframe = document.querySelector('iframe') as HTMLIFrameElement
    expect(iframe.src).toBe('https://player.bilibili.com/player.html?bvid=BV123')

    const link = document.querySelector('a[href*="bilibili.com"]') as HTMLAnchorElement
    expect(link.href).toBe('https://www.bilibili.com/video/BV123')
    expect(link.textContent).toContain('Mở trên Bilibili')
    expect(document.body.textContent).toContain('Video test')
  })

  it('gọi onClose khi đóng dialog', async () => {
    const onClose = vi.fn()
    const screen = await render(
      <VideoPreviewDialog
        title='Video test'
        embedUrl='https://www.youtube.com/embed/abc'
        externalUrl='https://www.youtube.com/watch?v=abc'
        externalLabel='Mở trên YouTube'
        onClose={onClose}
      />
    )

    // Radix Dialog: nút đóng mặc định có aria-label "Close".
    await screen.getByRole('button', { name: /close/i }).click()
    expect(onClose).toHaveBeenCalledOnce()
  })
})
