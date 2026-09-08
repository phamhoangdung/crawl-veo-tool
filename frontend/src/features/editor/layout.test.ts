import { describe, expect, it } from 'vitest'
import type { TimelineClip } from '@/lib/api'
import {
  applyDragToClip,
  computeVideoTrackLayout,
  defaultVerticalCrop,
  getClipOutputRange,
  totalVideoDuration,
} from './layout'

function clip(overrides: Partial<TimelineClip> = {}): TimelineClip {
  return { start: 0, end: 2, ...overrides }
}

describe('computeVideoTrackLayout', () => {
  it('places a single clip starting at 0', () => {
    const layout = computeVideoTrackLayout([clip({ start: 0, end: 5 })])
    expect(layout).toEqual([{ clipIndex: 0, clip: layout[0].clip, outputStart: 0, outputEnd: 5 }])
  })

  it('places hard-cut clips back to back', () => {
    const clips = [clip({ start: 0, end: 5 }), clip({ start: 0, end: 3, transition_in: 'cut' })]
    const layout = computeVideoTrackLayout(clips)
    expect(layout[0]).toMatchObject({ outputStart: 0, outputEnd: 5 })
    expect(layout[1]).toMatchObject({ outputStart: 5, outputEnd: 8 })
  })

  it('overlaps fade-transition clips by transition_duration', () => {
    const clips = [
      clip({ start: 0, end: 5 }),
      clip({ start: 0, end: 3, transition_in: 'fade', transition_duration: 1 }),
    ]
    const layout = computeVideoTrackLayout(clips)
    expect(layout[0]).toMatchObject({ outputStart: 0, outputEnd: 5 })
    // clip 2 bắt đầu SỚM HƠN 1s so với hard-cut (5s) vì chồng lấn transition
    expect(layout[1]).toMatchObject({ outputStart: 4, outputEnd: 7 })
  })

  it('defaults fade transition_duration to 1 second when unspecified', () => {
    const clips = [clip({ start: 0, end: 2 }), clip({ start: 0, end: 2, transition_in: 'fade' })]
    const layout = computeVideoTrackLayout(clips)
    expect(layout[1].outputStart).toBe(1)
  })
})

describe('totalVideoDuration', () => {
  it('returns 0 for empty clips', () => {
    expect(totalVideoDuration([])).toBe(0)
  })

  it('returns the output end of the last clip', () => {
    const clips = [clip({ start: 0, end: 5 }), clip({ start: 0, end: 3, transition_in: 'cut' })]
    expect(totalVideoDuration(clips)).toBe(8)
  })
})

describe('getClipOutputRange', () => {
  it('uses computed layout for video track', () => {
    const clips = [clip({ start: 0, end: 5 }), clip({ start: 0, end: 3, transition_in: 'cut' })]
    const layout = computeVideoTrackLayout(clips)
    const range = getClipOutputRange({ type: 'video', clips }, 1, layout)
    expect(range).toEqual({ start: 5, end: 8 })
  })

  it('uses track_start for audio track', () => {
    const track = {
      type: 'audio' as const,
      clips: [clip({ start: 0, end: 4, track_start: 10 })],
    }
    expect(getClipOutputRange(track, 0, [])).toEqual({ start: 10, end: 14 })
  })

  it('defaults audio track_start to 0 when unspecified', () => {
    const track = { type: 'audio' as const, clips: [clip({ start: 0, end: 4 })] }
    expect(getClipOutputRange(track, 0, [])).toEqual({ start: 0, end: 4 })
  })

  it('uses start/end directly for overlay track', () => {
    const track = {
      type: 'overlay' as const,
      clips: [clip({ text: 'hi', start: 3, end: 6 })],
    }
    expect(getClipOutputRange(track, 0, [])).toEqual({ start: 3, end: 6 })
  })
})

describe('applyDragToClip', () => {
  it('resize-start moves the start earlier/later without crossing end', () => {
    const c = clip({ start: 2, end: 5 })
    expect(applyDragToClip(c, 'video', 'resize-start', 1)).toEqual({ start: 3 })
    expect(applyDragToClip(c, 'video', 'resize-start', -10)).toEqual({ start: 0 })
    // Không cho start vượt quá end - MIN_CLIP_DURATION
    expect(applyDragToClip(c, 'video', 'resize-start', 10)).toEqual({ start: 4.9 })
  })

  it('resize-end moves the end without crossing start', () => {
    const c = clip({ start: 2, end: 5 })
    expect(applyDragToClip(c, 'video', 'resize-end', 2)).toEqual({ end: 7 })
    expect(applyDragToClip(c, 'video', 'resize-end', -10)).toEqual({ end: 2.1 })
  })

  it('move on audio track shifts track_start, clamped to 0', () => {
    const c = clip({ start: 0, end: 4, track_start: 5 })
    expect(applyDragToClip(c, 'audio', 'move', 2)).toEqual({ track_start: 7 })
    expect(applyDragToClip(c, 'audio', 'move', -100)).toEqual({ track_start: 0 })
  })

  it('move on overlay track shifts start and end together, preserving duration', () => {
    const c = clip({ text: 'hi', start: 3, end: 6 })
    expect(applyDragToClip(c, 'overlay', 'move', 2)).toEqual({ start: 5, end: 8 })
  })

  it('move on video track is a no-op (order determines position, not drag)', () => {
    const c = clip({ start: 0, end: 5 })
    expect(applyDragToClip(c, 'video', 'move', 3)).toEqual({})
  })
})

describe('defaultVerticalCrop', () => {
  it('produces a centered 9:16 box for a wide landscape video', () => {
    const crop = defaultVerticalCrop(1920, 1080)
    expect(crop.height).toBe(1080)
    expect(crop.width).toBe(Math.round((1080 * 9) / 16))
    expect(crop.x).toBe(Math.round((1920 - crop.width) / 2))
    expect(crop.y).toBe(0)
  })

  it('clamps width to video width when the video is already narrow', () => {
    const crop = defaultVerticalCrop(400, 1080)
    expect(crop.width).toBe(400)
    expect(crop.x).toBe(0)
  })
})

describe('getClipOutputRange — track ảnh (logo/watermark)', () => {
  const videoLayout = computeVideoTrackLayout([
    { source: 'a.mp4', start: 0, end: 10 },
  ])

  it('logo không có mốc thời gian trải suốt chiều dài video', () => {
    // Trước đây trả về undefined rồi thành NaN khi tính bề rộng — clip biến mất.
    const track = { type: 'image' as const, clips: [{ source: 'logo.png', x: 0.85 }] }

    expect(getClipOutputRange(track, 0, videoLayout)).toEqual({ start: 0, end: 10 })
  })

  it('không sinh NaN khi chưa có track video nào', () => {
    const track = { type: 'image' as const, clips: [{ source: 'logo.png' }] }
    const range = getClipOutputRange(track, 0, [])

    expect(Number.isNaN(range.end - range.start)).toBe(false)
  })

  it('logo có mốc thời gian dùng đúng mốc đó', () => {
    const track = {
      type: 'image' as const,
      clips: [{ source: 'logo.png', start: 2, end: 6 }],
    }

    expect(getClipOutputRange(track, 0, videoLayout)).toEqual({ start: 2, end: 6 })
  })
})
