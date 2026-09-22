import { render } from 'vitest-browser-react'
import { beforeEach, describe, expect, it } from 'vitest'
import '@/styles/index.css'
import type { TimelineOperations } from '@/lib/api'
import { ImageLayer } from './image-layer'
import { useEditorStore } from './store'

function dispatchPointer(el: EventTarget, type: string, x: number, y: number) {
  el.dispatchEvent(
    new PointerEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, pointerId: 1 })
  )
}

const OPERATIONS: TimelineOperations = {
  tracks: [
    { type: 'video', clips: [{ source: 'a.mp4', start: 0, end: 10 }] },
    { type: 'image', clips: [{ source: 'logo.png', x: 0.85, y: 0.12, width: 0.15, opacity: 0.85 }] },
  ],
}

function Harness() {
  return (
    <div style={{ position: 'relative', width: 400, height: 300 }}>
      <ImageLayer currentTime={0} />
    </div>
  )
}

describe('ImageLayer', () => {
  beforeEach(() => {
    useEditorStore.setState({
      operations: structuredClone(OPERATIONS),
      past: [],
      future: [],
      selected: null,
      gestureSnapshot: null,
    })
  })

  it('hiện logo đúng vị trí theo tỉ lệ khung hình', async () => {
    await render(<Harness />)
    const box = document.querySelector('[data-testid=image-box-0]') as HTMLElement

    expect(box).not.toBeNull()
    // 0.85 * 400 = 340px (tâm ảnh, -translate-x-1/2 nên left CSS vẫn là 340px)
    expect(box.getBoundingClientRect().left + box.getBoundingClientRect().width / 2).toBeCloseTo(340, 0)
  })

  it('kéo cả khung thì đổi x/y', async () => {
    await render(<Harness />)
    const box = document.querySelector('[data-testid=image-box-0]')!

    dispatchPointer(box, 'pointerdown', 340, 36)
    dispatchPointer(window, 'pointermove', 300, 66)
    dispatchPointer(window, 'pointerup', 300, 66)

    const clip = useEditorStore.getState().operations.tracks[1].clips[0]
    // Kéo -40px trên khung 400px = -0.1
    expect(clip.x).toBeCloseTo(0.75, 2)
    expect(clip.y).toBeCloseTo(0.22, 2)
    expect(clip.width).toBe(0.15)
  })

  it('kéo qua nhiều pointermove chỉ tốn đúng 1 bước undo, và undo trả về đúng vị trí gốc', async () => {
    await render(<Harness />)
    const box = document.querySelector('[data-testid=image-box-0]')!

    dispatchPointer(box, 'pointerdown', 340, 36)
    for (let i = 1; i <= 15; i++) {
      dispatchPointer(window, 'pointermove', 340 - i, 36 + i)
    }
    dispatchPointer(window, 'pointerup', 325, 51)

    expect(useEditorStore.getState().past).toHaveLength(1)

    useEditorStore.getState().undo()
    const clip = useEditorStore.getState().operations.tracks[1].clips[0]
    expect(clip.x).toBe(0.85)
    expect(clip.y).toBe(0.12)
  })

  it('kéo góc dưới-phải thì đổi width, không đổi vị trí', async () => {
    await render(<Harness />)
    const handle = document.querySelector('[data-testid=image-resize-0]')!

    dispatchPointer(handle, 'pointerdown', 370, 50)
    dispatchPointer(window, 'pointermove', 410, 50)
    dispatchPointer(window, 'pointerup', 410, 50)

    const clip = useEditorStore.getState().operations.tracks[1].clips[0]
    // Kéo +40px trên khung 400px = +0.1
    expect(clip.width).toBeCloseTo(0.25, 2)
    expect(clip.x).toBe(0.85)
    expect(clip.y).toBe(0.12)
  })

  it('ẩn logo ngoài khoảng thời gian của nó', async () => {
    useEditorStore.setState({
      operations: {
        tracks: [
          { type: 'video', clips: [{ source: 'a.mp4', start: 0, end: 10 }] },
          {
            type: 'image',
            clips: [{ source: 'logo.png', x: 0.1, y: 0.1, width: 0.1, start: 5, end: 8 }],
          },
        ],
      },
    })
    await render(
      <div style={{ position: 'relative', width: 400, height: 300 }}>
        <ImageLayer currentTime={2} />
      </div>
    )

    expect(document.querySelector('[data-testid=image-box-0]')).toBeNull()
  })

  it('logo không có mốc thời gian thì hiện suốt video', async () => {
    await render(
      <div style={{ position: 'relative', width: 400, height: 300 }}>
        <ImageLayer currentTime={99} />
      </div>
    )

    expect(document.querySelector('[data-testid=image-box-0]')).not.toBeNull()
  })
})
