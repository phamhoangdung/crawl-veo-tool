import type { CropBox, TimelineClip, TimelineTrack } from '@/lib/api'

/**
 * A clip whose timestamps definitely exist.
 *
 * `TimelineClip.start/end` are optional because image clips (a logo shown for the whole video) and
 * blur regions may leave them empty. But clips on **video/audio/overlay** tracks
 * always have them: the backend refuses to save a timeline missing them (see
 * `timeline_service.validate_operations`), and only those three track kinds go through
 * the geometry functions here.
 *
 * Declare this invariant once, instead of scattering `!` in ~20 places — each scattered `!`
 * is a separate assertion nobody can check, while here it has a name, a
 * reason, and fixing one place is enough if the invariant changes.
 */
export type TimedClip = TimelineClip & { start: number; end: number }

export function asTimed(clip: TimelineClip): TimedClip {
  return clip as TimedClip
}

export const DEFAULT_PX_PER_SECOND = 40
export const MIN_PX_PER_SECOND = 5
export const MAX_PX_PER_SECOND = 400

/** Keep the old name for code/tests already using it; zoom passes its own scale through a parameter. */
export const PX_PER_SECOND = DEFAULT_PX_PER_SECOND
export const MIN_CLIP_DURATION = 0.1

/** Default 9:16 vertical crop, horizontally centered — a sensible starting point for
 * most landscape videos before the user drags to adjust again (Phase 11). */
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
 * Position of video clips on the overall (output) timeline — clips follow one another, a clip with
 * `transition_in: 'fade'` overlaps by `transition_duration` seconds with the clip right
 * before it — matching exactly how the backend computes `cumulative_duration` in
 * `app/adapters/ffmpeg.py::render_timeline`, so the UI shows the real position that will be
 * rendered, not drifting from the final result.
 */
export function computeVideoTrackLayout(clips: TimelineClip[]): LayoutedClip[] {
  const result: LayoutedClip[] = []
  let cumulative = 0

  clips.forEach((rawClip, index) => {
    const clip = asTimed(rawClip)
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

/** Display position of 1 clip by track kind — video uses the computed layout (position inferred
 * from order), audio/overlay use the position declared directly in the clip. */
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
    return { start, end: start + ((clip.end ?? 0) - (clip.start ?? 0)) }
  }
  if (track.type === 'image' && (clip.start == null || clip.end == null)) {
    // A logo that declares no time range means it shows for the whole video — draw it across the full
    // timeline length instead of letting undefined slip down into a subtraction and become NaN.
    const videoEnd = videoLayout.at(-1)?.outputEnd ?? 0
    return { start: 0, end: videoEnd }
  }
  // overlay + image have time ranges
  return { start: clip.start ?? 0, end: clip.end ?? 0 }
}

export type DragMode = 'move' | 'resize-start' | 'resize-end'

/**
 * Compute the patch to apply to 1 clip when dragging — a pure function, touching no DOM/state, so it can be tested
 * independently of real mouse interaction (hard to test reliably via simulated pointer events).
 */
export function applyDragToClip(
  rawClip: TimelineClip,
  trackType: TimelineTrack['type'],
  mode: DragMode,
  deltaSeconds: number
): Partial<TimelineClip> {
  const clip = asTimed(rawClip)
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
  // Video track: the output position is decided by clip order, there is no independent
  // "move the clip body" meaning — only resizing the 2 ends is supported (changing the source trim range).
  return {}
}
