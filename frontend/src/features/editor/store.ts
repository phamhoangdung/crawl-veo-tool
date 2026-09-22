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
  /** Snapshot lúc bắt đầu 1 cử chỉ kéo (drag); null khi không đang kéo. */
  gestureSnapshot: TimelineOperations | null
  beginGesture: () => void
  endGesture: () => void
  /** Cắt đôi clip tại giây `atSeconds` (tính trên timeline output). */
  splitClip: (trackIndex: number, clipIndex: number, atSeconds: number) => void
  duplicateClip: (trackIndex: number, clipIndex: number) => void
  moveClip: (trackIndex: number, clipIndex: number, direction: -1 | 1) => void
  /** Thêm clip vào track có sẵn cùng type+role, hoặc tạo track mới nếu chưa có. */
  addClipToTrack: (
    type: TimelineTrack['type'],
    clip: TimelineClip,
    role?: string
  ) => void
  setOperations: (operations: TimelineOperations) => void
  updateClip: (trackIndex: number, clipIndex: number, patch: Partial<TimelineClip>) => void
  /** Như `updateClip` nhưng KHÔNG đẩy lịch sử — dùng trong lúc đang kéo
   * (`pointermove`), giữa `beginGesture`/`endGesture`. `updateClip` đẩy 1 bước
   * lịch sử mỗi lần gọi nên trước đây 1 cú kéo dài (~60-120 lần/giây) tiêu hết
   * cả 50 bước lịch sử — Undo sau khi kéo gần như vô dụng (xem `endGesture`). */
  updateClipDuringGesture: (
    trackIndex: number,
    clipIndex: number,
    patch: Partial<TimelineClip>
  ) => void
  /** Áp cùng 1 patch cho MỌI clip của 1 track, trong 1 bước lịch sử duy nhất —
   * dùng cho style áp cả track (vd font phụ đề). Gọi `updateClip` lặp lại từng
   * clip sẽ đẩy N bước undo riêng cho 1 thay đổi khái niệm là 1 bước. */
  updateTrackClips: (trackIndex: number, patch: Partial<TimelineClip>) => void
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
      // Track video phải đứng đầu: intro/outro nối vào đúng chỗ và renderer lấy
      // track video đầu tiên làm nền.
      const tracks =
        type === 'video' ? [track, ...state.operations.tracks] : [...state.operations.tracks, track]
      return withHistory(state, { tracks })
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

  updateClipDuringGesture: (trackIndex, clipIndex, patch) =>
    set((state) => ({
      operations: mapTrack(state.operations, trackIndex, (track) => ({
        ...track,
        clips: track.clips.map((clip, i) => (i === clipIndex ? { ...clip, ...patch } : clip)),
      })),
    })),

  beginGesture: () => {
    if (get().gestureSnapshot !== null) return // đã trong cử chỉ, không chồng lấn
    set((state) => ({ gestureSnapshot: state.operations }))
  },

  endGesture: () =>
    set((state) => {
      const snapshot = state.gestureSnapshot
      if (snapshot === null) return {}
      // Click (không thực kéo) thì đừng tiêu 1 ô lịch sử — so sánh nông đủ dùng
      // vì object gốc chỉ đổi khi có patch thật (mapTrack luôn tạo mảng/track
      // mới), snapshot khác state.operations về REFERENCE ngay khi có ít nhất 1
      // `updateClipDuringGesture` xảy ra.
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
      const rawClip = track?.clips[clipIndex]
      if (!rawClip) return state
      const clip = asTimed(rawClip)

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
