import { render } from 'vitest-browser-react'
import { describe, expect, it } from 'vitest'
import '@/styles/index.css'
import { ThumbPreview } from './thumb-preview'

const SRC = 'https://i1.hdslb.com/bfs/archive/abc.jpg'

describe('ThumbPreview', () => {
  it('hiện ảnh to hơn hẳn thumb khi hover', async () => {
    const screen = await render(<ThumbPreview src={SRC} className='w-28 rounded' />)
    const thumb = document.querySelector('img')!
    const thumbWidth = thumb.getBoundingClientRect().width

    await screen.getByRole('button').hover()
    await new Promise((r) => setTimeout(r, 200))

    const imgs = [...document.querySelectorAll('img')]
    expect(imgs.length).toBeGreaterThan(1)
    const largest = Math.max(...imgs.map((i) => i.getBoundingClientRect().width))
    // Thumb 112px -> ảnh xem trước 320px (w-80).
    expect(largest).toBeGreaterThan(thumbWidth * 2)
  })

  it('không bọc tooltip khi không có ảnh', async () => {
    await render(<ThumbPreview src={null} className='w-28' />)

    // Hiện khung rỗng to lên thì chẳng để làm gì.
    expect(document.querySelector('button')).toBeNull()
  })
})
