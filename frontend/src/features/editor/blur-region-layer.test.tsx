import { render } from 'vitest-browser-react'
import { beforeEach, describe, expect, it } from 'vitest'
import '@/styles/index.css'
import type { TimelineOperations } from '@/lib/api'
import { BlurRegionLayer } from './blur-region-layer'
import { useEditorStore } from './store'

function dispatchPointer(el: EventTarget, type: string, x: number, y: number) {
  el.dispatchEvent(
    new PointerEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, pointerId: 1 })
  )
}

const OPERATIONS: TimelineOperations = {
  tracks: [
    { type: 'video', clips: [{ source: 'a.mp4', start: 0, end: 10 }] },
    { type: 'blur', clips: [{ x: 0.7, y: 0.05, width: 0.2, height: 0.1, strength: 20 }] },
  ],
}

function Harness() {
  return (
    <div style={{ position: 'relative', width: 400, height: 300 }}>
      <BlurRegionLayer currentTime={0} />
    </div>
  )
}

describe('BlurRegionLayer', () => {
  beforeEach(() => {
    useEditorStore.setState({
      operations: structuredClone(OPERATIONS),
      past: [],
      future: [],
      selected: null,
    })
  })

  it('hiện vùng che theo đúng tỉ lệ khung hình', async () => {
    await render(<Harness />)
    const box = document.querySelector('[data-testid=blur-region-0]') as HTMLElement

    expect(box).not.toBeNull()
    // 0.7 * 400 = 280px, 0.2 * 400 = 80px
    expect(box.getBoundingClientRect().width).toBeCloseTo(80, 0)
  })

  it('kéo cả khung thì đổi x/y, không đổi kích thước', async () => {
    await render(<Harness />)
    const box = document.querySelector('[data-testid=blur-region-0]')!

    dispatchPointer(box, 'pointerdown', 300, 50)
    dispatchPointer(window, 'pointermove', 260, 80)
    dispatchPointer(window, 'pointerup', 260, 80)

    const clip = useEditorStore.getState().operations.tracks[1].clips[0]
    // Kéo -40px trên khung 400px = -0.1
    expect(clip.x).toBeCloseTo(0.6, 2)
    expect(clip.y).toBeCloseTo(0.15, 2)
    expect(clip.width).toBe(0.2)
    expect(clip.height).toBe(0.1)
  })

  it('kéo góc dưới-phải thì đổi kích thước, không đổi vị trí', async () => {
    await render(<Harness />)
    const handle = document.querySelector('[data-testid=blur-resize-0]')!

    dispatchPointer(handle, 'pointerdown', 300, 50)
    dispatchPointer(window, 'pointermove', 340, 80)
    dispatchPointer(window, 'pointerup', 340, 80)

    const clip = useEditorStore.getState().operations.tracks[1].clips[0]
    expect(clip.width).toBeCloseTo(0.3, 2)
    expect(clip.x).toBe(0.7)
  })

  it('không cho kéo tràn ra ngoài khung', async () => {
    await render(<Harness />)
    const box = document.querySelector('[data-testid=blur-region-0]')!

    // Kéo mạnh sang phải: vùng che tràn ra ngoài làm ffmpeg crop lỗi.
    dispatchPointer(box, 'pointerdown', 300, 50)
    dispatchPointer(window, 'pointermove', 900, 600)
    dispatchPointer(window, 'pointerup', 900, 600)

    const clip = useEditorStore.getState().operations.tracks[1].clips[0]
    expect(clip.x! + clip.width!).toBeLessThanOrEqual(1.001)
    expect(clip.y! + clip.height!).toBeLessThanOrEqual(1.001)
  })

  it('xoá được vùng che', async () => {
    const screen = await render(<Harness />)
    await screen.getByLabelText('Xoá vùng che').click()

    expect(useEditorStore.getState().operations.tracks[1].clips).toHaveLength(0)
  })

  it('ẩn vùng che ngoài khoảng thời gian của nó', async () => {
    useEditorStore.setState({
      operations: {
        tracks: [
          { type: 'video', clips: [{ source: 'a.mp4', start: 0, end: 10 }] },
          { type: 'blur', clips: [{ x: 0.1, y: 0.1, width: 0.2, height: 0.1, start: 5, end: 8 }] },
        ],
      },
    })
    await render(
      <div style={{ position: 'relative', width: 400, height: 300 }}>
        <BlurRegionLayer currentTime={2} />
      </div>
    )

    expect(document.querySelector('[data-testid=blur-region-0]')).toBeNull()
  })

  it('vùng che không có mốc thời gian thì hiện suốt video', async () => {
    await render(
      <div style={{ position: 'relative', width: 400, height: 300 }}>
        <BlurRegionLayer currentTime={99} />
      </div>
    )

    expect(document.querySelector('[data-testid=blur-region-0]')).not.toBeNull()
  })
})
