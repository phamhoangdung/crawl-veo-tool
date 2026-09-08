import type { CropBox, TimelineClip, TimelineTrack } from '@/lib/api'

export const DEFAULT_PX_PER_SECOND = 40
export const MIN_PX_PER_SECOND = 5
export const MAX_PX_PER_SECOND = 400

/** Giữ tên cũ cho code/test đã dùng; zoom truyền tỉ lệ riêng qua tham số. */
export const PX_PER_SECOND = DEFAULT_PX_PER_SECOND
export const MIN_CLIP_DURATION = 0.1

/** Crop dọc 9:16 mặc định, canh giữa theo chiều ngang — điểm bắt đầu hợp lý cho
 * hầu hết video ngang trước khi user tự kéo chỉnh lại (Phase 11). */
export function defaultVerticalCrop(videoWidth: number, videoHeight: number): CropBox {
  const width = Math.round((videoHeight * 9) / 16)
  const clampedWidth = Math.min(width, videoWidth)
  return {
    x: Math.round((videoWidth - clampedWidth) / 2),
    y: 0,
    width: clampedWidth,
    height: videoHeight,
  }
}

export function secondsToPx(seconds: number, pxPerSecond = DEFAULT_PX_PER_SECOND): number {
  return seconds * pxPerSecond
}

export function pxToSeconds(px: number, pxPerSecond = DEFAULT_PX_PER_SECOND): number {
  return px / pxPerSecond
}

export interface LayoutedClip {
  clipIndex: number
  clip: TimelineClip
  outputStart: number
  outputEnd: number
}

/**
 * Vị trí clip video trên timeline tổng (output) — các clip nối tiếp nhau, clip có
 * `transition_in: 'fade'` chồng lấn `transition_duration` giây với clip ngay
 * trước — khớp đúng cách backend tính `cumulative_duration` ở
 * `app/adapters/ffmpeg.py::render_timeline`, để UI hiển thị đúng vị trí thật sẽ
 * render ra, không lệch với kết quả cuối.
 */
export function computeVideoTrackLayout(clips: TimelineClip[]): LayoutedClip[] {
  const result: LayoutedClip[] = []
  let cumulative = 0

  clips.forEach((clip, index) => {
    const duration = clip.end - clip.start
    const transitionDuration =
      index > 0 && clip.transition_in === 'fade' ? (clip.transition_duration ?? 1) : 0
    const outputStart = index === 0 ? 0 : Math.max(0, cumulative - transitionDuration)
    const outputEnd = outputStart + duration
    result.push({ clipIndex: index, clip, outputStart, outputEnd })
    cumulative = outputEnd
  })

  return result
}

export function totalVideoDuration(clips: TimelineClip[]): number {
  const layout = computeVideoTrackLayout(clips)
  return layout.length > 0 ? layout[layout.length - 1].outputEnd : 0
}

/** Vị trí hiển thị 1 clip theo loại track — video dùng layout đã tính (vị trí suy
 * ra từ thứ tự), audio/overlay dùng vị trí tự khai báo trực tiếp trong clip. */
export function getClipOutputRange(
  track: TimelineTrack,
  clipIndex: number,
  videoLayout: LayoutedClip[]
): { start: number; end: number } {
  if (track.type === 'video') {
    const layouted = videoLayout[clipIndex]
    return layouted
      ? { start: layouted.outputStart, end: layouted.outputEnd }
      : { start: 0, end: 0 }
  }
  const clip = track.clips[clipIndex]
  if (track.type === 'audio') {
    const start = clip.track_start ?? 0
    return { start, end: start + (clip.end - clip.start) }
  }
  // overlay
  return { start: clip.start, end: clip.end }
}

export type DragMode = 'move' | 'resize-start' | 'resize-end'

/**
 * Tính patch cần áp cho 1 clip khi kéo — thuần hàm, không đụng DOM/state, để test
 * độc lập với tương tác chuột thật (khó test tin cậy qua giả lập pointer event).
 */
export function applyDragToClip(
  clip: TimelineClip,
  trackType: TimelineTrack['type'],
  mode: DragMode,
  deltaSeconds: number
): Partial<TimelineClip> {
  if (mode === 'resize-start') {
    const newStart = Math.max(0, Math.min(clip.start + deltaSeconds, clip.end - MIN_CLIP_DURATION))
    return { start: newStart }
  }

  if (mode === 'resize-end') {
    const newEnd = Math.max(clip.start + MIN_CLIP_DURATION, clip.end + deltaSeconds)
    return { end: newEnd }
  }

  // mode === 'move'
  if (trackType === 'audio') {
    return { track_start: Math.max(0, (clip.track_start ?? 0) + deltaSeconds) }
  }
  if (trackType === 'overlay') {
    const duration = clip.end - clip.start
    const newStart = Math.max(0, clip.start + deltaSeconds)
    return { start: newStart, end: newStart + duration }
  }
  // Track video: vị trí output do thứ tự clip quyết định, không có ý nghĩa "di
  // chuyển thân clip" độc lập — chỉ hỗ trợ resize 2 đầu (đổi đoạn trim nguồn).
  return {}
}
