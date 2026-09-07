import { beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import type { TimelineOperations } from '@/lib/api'
import { PX_PER_SECOND } from './layout'
import { useEditorStore } from './store'
import { Timeline } from './timeline'

function dispatchPointer(el: EventTarget, type: string, clientX: number) {
  el.dispatchEvent(
    new PointerEvent(type, { bubbles: true, cancelable: true, clientX, pointerId: 1 })
  )
}

const OPERATIONS: TimelineOperations = {
  tracks: [
    {
      type: 'video',
      clips: [
        { source: 'a.mp4', start: 0, end: 5 },
        { source: 'b.mp4', start: 0, end: 3, transition_in: 'cut' },
      ],
    },
    {
      type: 'audio',
      role: 'voice',
      clips: [{ source: 'voice.mp3', start: 0, end: 5, track_start: 0, volume: 1 }],
    },
  ],
}

beforeEach(() => {
  useEditorStore.setState({ operations: OPERATIONS, selected: null })
})

describe('Timeline', () => {
  it('renders a clip box for every clip in every track', async () => {
    const screen = await render(<Timeline />)
    await expect.element(screen.getByTestId('clip-0-0')).toBeInTheDocument()
    await expect.element(screen.getByTestId('clip-0-1')).toBeInTheDocument()
    await expect.element(screen.getByTestId('clip-1-0')).toBeInTheDocument()
  })

  it('positions the second video clip right after the first (hard cut)', async () => {
    const screen = await render(<Timeline />)
    const secondClip = screen.getByTestId('clip-0-1').element() as HTMLElement
    expect(secondClip.style.left).toBe(`${5 * PX_PER_SECOND}px`)
  })

  it('selects a clip on pointer down', async () => {
    const screen = await render(<Timeline />)
    const clip = screen.getByTestId('clip-1-0').element() as HTMLElement
    dispatchPointer(clip, 'pointerdown', 100)
    dispatchPointer(window, 'pointerup', 100)
    expect(useEditorStore.getState().selected).toEqual({ trackIndex: 1, clipIndex: 0 })
  })

  it('dragging the right edge of an audio clip extends its end time', async () => {
    const screen = await render(<Timeline />)
    const handle = screen.getByTestId('resize-end-1-0').element() as HTMLElement

    dispatchPointer(handle, 'pointerdown', 0)
    dispatchPointer(window, 'pointermove', PX_PER_SECOND * 2)
    dispatchPointer(window, 'pointerup', PX_PER_SECOND * 2)

    const clip = useEditorStore.getState().operations.tracks[1].clips[0]
    expect(clip.end).toBeCloseTo(7, 1) // 5 + 2s kéo
  })

  it('dragging the body of an audio clip moves track_start, not the video track', async () => {
    const screen = await render(<Timeline />)
    const clip = screen.getByTestId('clip-1-0').element() as HTMLElement

    dispatchPointer(clip, 'pointerdown', 0)
    dispatchPointer(window, 'pointermove', PX_PER_SECOND * 3)
    dispatchPointer(window, 'pointerup', PX_PER_SECOND * 3)

    const audioClip = useEditorStore.getState().operations.tracks[1].clips[0]
    expect(audioClip.track_start).toBeCloseTo(3, 1)
  })

  it('shows the empty state when there are no tracks', async () => {
    useEditorStore.setState({ operations: { tracks: [] }, selected: null })
    const screen = await render(<Timeline />)
    await expect.element(screen.getByText(/Chưa có timeline/)).toBeInTheDocument()
  })
})
