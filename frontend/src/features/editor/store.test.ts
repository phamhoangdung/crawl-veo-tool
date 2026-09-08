import { beforeEach, describe, expect, it } from 'vitest'
import type { TimelineOperations } from '@/lib/api'
import { useEditorStore } from './store'

function makeOps(): TimelineOperations {
  return {
    tracks: [
      {
        type: 'video',
        clips: [
          { source: 'a.mp4', start: 0, end: 10 },
          { source: 'b.mp4', start: 0, end: 5 },
        ],
      },
      {
        type: 'audio',
        role: 'voice',
        clips: [{ source: 'v.mp3', start: 0, end: 10, track_start: 2, volume: 1 }],
      },
    ],
  }
}

beforeEach(() => {
  useEditorStore.setState({
    operations: makeOps(),
    selected: null,
    past: [],
    future: [],
  })
})

describe('splitClip', () => {
  it('cắt clip video thành 2 tại vị trí playhead', () => {
    // Clip video 0 chiếm output 0→10; cắt tại giây 4.
    useEditorStore.getState().splitClip(0, 0, 4)

    const clips = useEditorStore.getState().operations.tracks[0].clips
    expect(clips).toHaveLength(3)
    expect(clips[0]).toMatchObject({ start: 0, end: 4 })
    expect(clips[1]).toMatchObject({ start: 4, end: 10 })
  })

  it('dời track_start cho nửa sau của clip audio', () => {
    // Clip audio đặt tại track_start=2, dài 10s → output 2→12. Cắt tại giây 5
    // nghĩa là offset 3 trong nguồn.
    useEditorStore.getState().splitClip(1, 0, 5)

    const clips = useEditorStore.getState().operations.tracks[1].clips
    expect(clips).toHaveLength(2)
    expect(clips[0]).toMatchObject({ start: 0, end: 3 })
    expect(clips[1]).toMatchObject({ start: 3, end: 10, track_start: 5 })
  })

  it('bỏ qua khi cắt sát mép — tránh tạo clip 0 giây', () => {
    useEditorStore.getState().splitClip(0, 0, 0.01)
    expect(useEditorStore.getState().operations.tracks[0].clips).toHaveLength(2)

    useEditorStore.getState().splitClip(0, 0, 9.99)
    expect(useEditorStore.getState().operations.tracks[0].clips).toHaveLength(2)
  })
})

describe('duplicateClip', () => {
  it('chèn bản sao ngay sau bản gốc', () => {
    useEditorStore.getState().duplicateClip(0, 0)

    const clips = useEditorStore.getState().operations.tracks[0].clips
    expect(clips).toHaveLength(3)
    expect(clips[1]).toMatchObject({ source: 'a.mp4', start: 0, end: 10 })
  })

  it('dời bản sao audio ra sau để không chồng tiếng', () => {
    useEditorStore.getState().duplicateClip(1, 0)

    const clips = useEditorStore.getState().operations.tracks[1].clips
    expect(clips[0].track_start).toBe(2)
    // Bản gốc chiếm 2→12 nên bản sao bắt đầu ở 12.
    expect(clips[1].track_start).toBe(12)
  })
})

describe('moveClip', () => {
  it('đổi chỗ 2 clip và giữ vùng chọn theo clip đã di chuyển', () => {
    useEditorStore.getState().moveClip(0, 0, 1)

    const clips = useEditorStore.getState().operations.tracks[0].clips
    expect(clips[0].source).toBe('b.mp4')
    expect(clips[1].source).toBe('a.mp4')
    expect(useEditorStore.getState().selected).toEqual({ trackIndex: 0, clipIndex: 1 })
  })

  it('không làm gì khi ra ngoài phạm vi', () => {
    useEditorStore.getState().moveClip(0, 0, -1)
    expect(useEditorStore.getState().operations.tracks[0].clips[0].source).toBe('a.mp4')
  })
})

describe('undo/redo', () => {
  it('hoàn tác trả về trạng thái trước đó', () => {
    useEditorStore.getState().removeClip(0, 1)
    expect(useEditorStore.getState().operations.tracks[0].clips).toHaveLength(1)

    useEditorStore.getState().undo()
    expect(useEditorStore.getState().operations.tracks[0].clips).toHaveLength(2)
  })

  it('làm lại khôi phục thay đổi vừa hoàn tác', () => {
    useEditorStore.getState().removeClip(0, 1)
    useEditorStore.getState().undo()
    useEditorStore.getState().redo()

    expect(useEditorStore.getState().operations.tracks[0].clips).toHaveLength(1)
  })

  it('thao tác mới xoá nhánh redo', () => {
    useEditorStore.getState().removeClip(0, 1)
    useEditorStore.getState().undo()
    useEditorStore.getState().duplicateClip(0, 0)

    expect(useEditorStore.getState().future).toHaveLength(0)
  })

  it('nạp timeline mới xoá sạch lịch sử', () => {
    useEditorStore.getState().removeClip(0, 1)
    useEditorStore.getState().setOperations(makeOps())

    expect(useEditorStore.getState().past).toHaveLength(0)
    expect(useEditorStore.getState().future).toHaveLength(0)
  })
})

describe('zoom', () => {
  it('kẹp trong khoảng cho phép', () => {
    useEditorStore.getState().setZoom(99999)
    expect(useEditorStore.getState().pxPerSecond).toBeLessThanOrEqual(400)

    useEditorStore.getState().setZoom(0.001)
    expect(useEditorStore.getState().pxPerSecond).toBeGreaterThanOrEqual(5)
  })
})

describe('requestSeek', () => {
  it('tăng nonce để chọn lại cùng clip vẫn tua lại được', () => {
    useEditorStore.getState().requestSeek(5)
    const first = useEditorStore.getState().seekRequest
    useEditorStore.getState().requestSeek(5)
    const second = useEditorStore.getState().seekRequest

    expect(second?.seconds).toBe(5)
    expect(second?.nonce).toBeGreaterThan(first?.nonce ?? 0)
  })
})
