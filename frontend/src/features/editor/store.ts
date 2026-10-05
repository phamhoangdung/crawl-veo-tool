import { create } from 'zustand'
import type { TimelineClip, TimelineOperations, TimelineTrack } from '@/lib/api'
import {
  asTimed,
  DEFAULT_PX_PER_SECOND,
  MAX_PX_PER_SECOND,
  MIN_PX_PER_SECOND,
} from './layout'

export interface Selection {
  trackIndex: number
  clipIndex: number
}

interface EditorStore {
  operations: TimelineOperations
  selected: Selection | null
  /**
   * Request to seek the video to this second. The timeline sets the value when the user selects a
   * clip; the preview frame responds and then clears it itself. Uses `{seconds, nonce}` rather than
   * a bare number so re-selecting the same old clip still seeks again.
   */
  seekRequest: { seconds: number; nonce: number } | null
  requestSeek: (seconds: number) => void
  consumeSeek: () => void
  /** Pixels per second on the timeline — zoom in/out to work with short clips. */
  pxPerSecond: number
  setZoom: (pxPerSecond: number) => void
  /** History for undo/redo; stores only `operations`, not the selection. */
  past: TimelineOperations[]
  future: TimelineOperations[]
  undo: () => void
  redo: () => void
  /** Snapshot at the start of a drag gesture; null when not dragging. */
  gestureSnapshot: TimelineOperations | null
  beginGesture: () => void
  endGesture: () => void
  /** Split a clip in two at second `atSeconds` (measured on the output timeline). */
  splitClip: (trackIndex: number, clipIndex: number, atSeconds: number) => void
  duplicateClip: (trackIndex: number, clipIndex: number) => void
  moveClip: (trackIndex: number, clipIndex: number, direction: -1 | 1) => void
  /** Add a clip to an existing track of the same type+role, or create a new track if there is none. */
  addClipToTrack: (
    type: TimelineTrack['type'],
    clip: TimelineClip,
    role?: string
  ) => void
  setOperations: (operations: TimelineOperations) => void
  updateClip: (trackIndex: number, clipIndex: number, patch: Partial<TimelineClip>) => void
  /** Like `updateClip` but does NOT push history — used while dragging
   * (`pointermove`), between `beginGesture`/`endGesture`. `updateClip` pushes 1 history
   * step per call so previously one long drag (~60-120 times/second) used up
   * all 50 history steps — Undo after a drag was nearly useless (see `endGesture`). */
  updateClipDuringGesture: (
    trackIndex: number,
    clipIndex: number,
    patch: Partial<TimelineClip>
  ) => void
  /** Apply the same patch to EVERY clip of a track, in a single history step —
   * used for track-wide style (e.g. subtitle font). Calling `updateClip` repeatedly per
   * clip would push N separate undo steps for one change that is conceptually 1 step. */
  updateTrackClips: (trackIndex: number, patch: Partial<TimelineClip>) => void
  removeClip: (trackIndex: number, clipIndex: number) => void
  select: (selection: Selection) => void
  clearSelection: () => void
}

const MAX_HISTORY = 50

/** Apply a change to operations, pushing the old version into history so it can be undone. */
function withHistory(
  state: { operations: TimelineOperations; past: TimelineOperations[] },
  next: TimelineOperations
) {
  return {
    operations: next,
    past: [...state.past, state.operations].slice(-MAX_HISTORY),
    // A new action discards the redo branch — like every other editor.
    future: [] as TimelineOperations[],
  }
}

function mapTrack(
  operations: TimelineOperations,
  trackIndex: number,
  fn: (track: TimelineOperations['tracks'][number]) => TimelineOperations['tracks'][number]
): TimelineOperations {
  return {
    tracks: operations.tracks.map((track, i) => (i === trackIndex ? fn(track) : track)),
  }
}

export const useEditorStore = create<EditorStore>((set, get) => ({
  operations: { tracks: [] },
  selected: null,
  seekRequest: null,
  pxPerSecond: DEFAULT_PX_PER_SECOND,
  past: [],
  future: [],
  gestureSnapshot: null,

  requestSeek: (seconds) =>
    set((state) => ({
      seekRequest: { seconds, nonce: (state.seekRequest?.nonce ?? 0) + 1 },
    })),

  consumeSeek: () => set({ seekRequest: null }),

  setZoom: (pxPerSecond) =>
    set({ pxPerSecond: Math.min(MAX_PX_PER_SECOND, Math.max(MIN_PX_PER_SECOND, pxPerSecond)) }),

  undo: () =>
    set((state) => {
      const previous = state.past.at(-1)
      if (!previous) return state
      return {
        operations: previous,
        past: state.past.slice(0, -1),
        future: [state.operations, ...state.future].slice(0, MAX_HISTORY),
        selected: null,
      }
    }),

  redo: () =>
    set((state) => {
      const next = state.future[0]
      if (!next) return state
      return {
        operations: next,
        past: [...state.past, state.operations].slice(-MAX_HISTORY),
        future: state.future.slice(1),
        selected: null,
      }
    }),

  addClipToTrack: (type, clip, role) =>
    set((state) => {
      const index = state.operations.tracks.findIndex(
        (t) => t.type === type && t.role === role
      )

      if (index >= 0) {
        return withHistory(
          state,
          mapTrack(state.operations, index, (t) => ({ ...t, clips: [...t.clips, clip] }))
        )
      }

      const track: TimelineTrack = { type, clips: [clip], ...(role ? { role } : {}) }
      // The video track must come first: intro/outro join in the right place and the renderer takes the
      // first video track as the base.
      const tracks =
        type === 'video' ? [track, ...state.operations.tracks] : [...state.operations.tracks, track]
      return withHistory(state, { tracks })
    }),

  // Load a new timeline (from the server or an AI suggestion) — clear history because this is a new starting point.
  setOperations: (operations) =>
    set({ operations, selected: null, past: [], future: [] }),

  updateClip: (trackIndex, clipIndex, patch) =>
    set((state) =>
      withHistory(
        state,
        mapTrack(state.operations, trackIndex, (track) => ({
          ...track,
          clips: track.clips.map((clip, i) => (i === clipIndex ? { ...clip, ...patch } : clip)),
        }))
      )
    ),

  updateClipDuringGesture: (trackIndex, clipIndex, patch) =>
    set((state) => ({
      operations: mapTrack(state.operations, trackIndex, (track) => ({
        ...track,
        clips: track.clips.map((clip, i) => (i === clipIndex ? { ...clip, ...patch } : clip)),
      })),
    })),

  beginGesture: () => {
    if (get().gestureSnapshot !== null) return // already in a gesture, no overlap
    set((state) => ({ gestureSnapshot: state.operations }))
  },

  endGesture: () =>
    set((state) => {
      const snapshot = state.gestureSnapshot
      if (snapshot === null) return {}
      // A click (not a real drag) should not spend 1 history slot — a shallow compare is enough
      // because the original object only changes when there is a real patch (mapTrack always creates a new
      // array/track), and the snapshot differs from state.operations by REFERENCE as soon as at least 1
      // `updateClipDuringGesture` has happened.
      if (snapshot === state.operations) return { gestureSnapshot: null }
      return {
        past: [...state.past, snapshot].slice(-MAX_HISTORY),
        future: [] as TimelineOperations[],
        gestureSnapshot: null,
      }
    }),

  updateTrackClips: (trackIndex, patch) =>
    set((state) =>
      withHistory(
        state,
        mapTrack(state.operations, trackIndex, (track) => ({
          ...track,
          clips: track.clips.map((clip) => ({ ...clip, ...patch })),
        }))
      )
    ),

  splitClip: (trackIndex, clipIndex, atSeconds) =>
    set((state) => {
      const track = state.operations.tracks[trackIndex]
      const rawClip = track?.clips[clipIndex]
      if (!rawClip) return state
      const clip = asTimed(rawClip)

      // `atSeconds` is the position on the output timeline; convert it to an offset within the source file.
      const offsetInClip =
        track.type === 'audio' ? atSeconds - (clip.track_start ?? 0) : atSeconds - clip.start
      const splitAt = clip.start + offsetInClip

      // Cutting right at an edge is skipped: creating a 0-second clip only clutters the timeline.
      if (splitAt <= clip.start + 0.05 || splitAt >= clip.end - 0.05) return state

      const first = { ...clip, end: splitAt }
      const second = {
        ...clip,
        start: splitAt,
        ...(track.type === 'audio'
          ? { track_start: (clip.track_start ?? 0) + (splitAt - clip.start) }
          : {}),
      }

      return {
        ...withHistory(
          state,
          mapTrack(state.operations, trackIndex, (t) => ({
            ...t,
            clips: [...t.clips.slice(0, clipIndex), first, second, ...t.clips.slice(clipIndex + 1)],
          }))
        ),
        selected: null,
      }
    }),

  duplicateClip: (trackIndex, clipIndex) =>
    set((state) => {
      const track = state.operations.tracks[trackIndex]
      const rawClip = track?.clips[clipIndex]
      if (!rawClip) return state
      const clip = asTimed(rawClip)

      // The audio copy is placed right after the original so the sounds do not overlap each other.
      const copy =
        track.type === 'audio'
          ? { ...clip, track_start: (clip.track_start ?? 0) + (clip.end - clip.start) }
          : { ...clip }

      return withHistory(
        state,
        mapTrack(state.operations, trackIndex, (t) => ({
          ...t,
          clips: [...t.clips.slice(0, clipIndex + 1), copy, ...t.clips.slice(clipIndex + 1)],
        }))
      )
    }),

  moveClip: (trackIndex, clipIndex, direction) =>
    set((state) => {
      const track = state.operations.tracks[trackIndex]
      const target = clipIndex + direction
      if (!track || target < 0 || target >= track.clips.length) return state

      const clips = [...track.clips]
      ;[clips[clipIndex], clips[target]] = [clips[target], clips[clipIndex]]

      return {
        ...withHistory(state, mapTrack(state.operations, trackIndex, (t) => ({ ...t, clips }))),
        selected: { trackIndex, clipIndex: target },
      }
    }),

  removeClip: (trackIndex, clipIndex) =>
    set((state) => ({
      ...withHistory(
        state,
        mapTrack(state.operations, trackIndex, (track) => ({
          ...track,
          clips: track.clips.filter((_, i) => i !== clipIndex),
        }))
      ),
      selected: null,
    })),

  select: (selection) => set({ selected: selection }),
  clearSelection: () => set({ selected: null }),
}))
