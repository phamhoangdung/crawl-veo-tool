import { create } from 'zustand'
import type { TimelineClip, TimelineOperations } from '@/lib/api'
import { DEFAULT_PX_PER_SECOND, MAX_PX_PER_SECOND, MIN_PX_PER_SECOND } from './layout'

export interface Selection {
  trackIndex: number
  clipIndex: number
}

interface EditorStore {
  operations: TimelineOperations
  selected: Selection | null
  /**
   * Yêu cầu tua video tới giây này. Timeline đặt giá trị khi người dùng chọn
   * clip; khung preview hưởng ứng rồi tự xoá. Dùng `{seconds, nonce}` chứ không
   * phải số trần để chọn lại đúng clip cũ vẫn tua lại được.
   */
  seekRequest: { seconds: number; nonce: number } | null
  requestSeek: (seconds: number) => void
  consumeSeek: () => void
  /** Số pixel mỗi giây trên timeline — zoom in/out để làm việc với clip ngắn. */
  pxPerSecond: number
  setZoom: (pxPerSecond: number) => void
  /** Lịch sử để undo/redo; chỉ lưu `operations`, không lưu vùng chọn. */
  past: TimelineOperations[]
  future: TimelineOperations[]
  undo: () => void
  redo: () => void
  /** Cắt đôi clip tại giây `atSeconds` (tính trên timeline output). */
  splitClip: (trackIndex: number, clipIndex: number, atSeconds: number) => void
  duplicateClip: (trackIndex: number, clipIndex: number) => void
  moveClip: (trackIndex: number, clipIndex: number, direction: -1 | 1) => void
  setOperations: (operations: TimelineOperations) => void
  updateClip: (trackIndex: number, clipIndex: number, patch: Partial<TimelineClip>) => void
  removeClip: (trackIndex: number, clipIndex: number) => void
  select: (selection: Selection) => void
  clearSelection: () => void
}

const MAX_HISTORY = 50

/** Áp thay đổi lên operations, đẩy bản cũ vào lịch sử để undo được. */
function withHistory(
  state: { operations: TimelineOperations; past: TimelineOperations[] },
  next: TimelineOperations
) {
  return {
    operations: next,
    past: [...state.past, state.operations].slice(-MAX_HISTORY),
    // Thao tác mới làm mất nhánh redo — giống mọi editor khác.
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

export const useEditorStore = create<EditorStore>((set) => ({
  operations: { tracks: [] },
  selected: null,
  seekRequest: null,
  pxPerSecond: DEFAULT_PX_PER_SECOND,
  past: [],
  future: [],

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

  // Nạp timeline mới (từ server hoặc gợi ý AI) — xoá lịch sử vì đây là điểm bắt đầu mới.
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

  splitClip: (trackIndex, clipIndex, atSeconds) =>
    set((state) => {
      const track = state.operations.tracks[trackIndex]
      const clip = track?.clips[clipIndex]
      if (!clip) return state

      // `atSeconds` là vị trí trên timeline output; quy về offset trong file nguồn.
      const offsetInClip =
        track.type === 'audio' ? atSeconds - (clip.track_start ?? 0) : atSeconds - clip.start
      const splitAt = clip.start + offsetInClip

      // Cắt sát mép thì bỏ qua: tạo clip 0 giây chỉ làm rối timeline.
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
      const clip = track?.clips[clipIndex]
      if (!clip) return state

      // Bản sao audio đặt ngay sau bản gốc để không chồng tiếng lên nhau.
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
