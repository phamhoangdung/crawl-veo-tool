import { create } from 'zustand'

/** Vị trí node trên canvas, theo scene id. */
export type NodePositions = Record<number, { x: number; y: number }>

interface FlowState {
  positions: NodePositions
  past: NodePositions[]
  future: NodePositions[]
  /** Snapshot lúc bắt đầu cử chỉ kéo; null khi không kéo. */
  gestureSnapshot: NodePositions | null
  dirty: boolean

  setPositions: (positions: NodePositions) => void
  moveNode: (sceneId: number, x: number, y: number) => void
  beginGesture: () => void
  endGesture: () => void
  undo: () => void
  redo: () => void
  markSaved: () => void
}

const MAX_HISTORY = 50

function samePositions(a: NodePositions, b: NodePositions): boolean {
  const aKeys = Object.keys(a)
  if (aKeys.length !== Object.keys(b).length) return false
  return aKeys.every((key) => {
    const id = Number(key)
    return a[id].x === b[id].x && a[id].y === b[id].y
  })
}

/**
 * Store cho canvas dựng video.
 *
 * Khác `features/editor/store.ts` ở chỗ undo/redo **gộp theo cử chỉ**: editor
 * push history mỗi `pointermove` nên một cú kéo tiêu hết stack 50 entry và undo
 * chỉ lùi được vài pixel. Ở đây `beginGesture`/`endGesture` (nối vào
 * `onNodeDragStart`/`onNodeDragStop` của React Flow) chỉ push đúng 1 entry cho
 * cả cú kéo.
 */
export const useFlowStore = create<FlowState>()((set, get) => ({
  positions: {},
  past: [],
  future: [],
  gestureSnapshot: null,
  dirty: false,

  // Nạp từ server: xoá history vì đây là mốc mới, không phải thao tác của người dùng.
  setPositions: (positions) =>
    set({ positions, past: [], future: [], gestureSnapshot: null, dirty: false }),

  moveNode: (sceneId, x, y) =>
    set((state) => ({
      positions: { ...state.positions, [sceneId]: { x, y } },
      dirty: true,
    })),

  beginGesture: () => {
    if (get().gestureSnapshot !== null) return // đã trong cử chỉ, không chồng lấn
    set((state) => ({ gestureSnapshot: state.positions }))
  },

  endGesture: () =>
    set((state) => {
      const snapshot = state.gestureSnapshot
      if (snapshot === null) return {}
      // Click (không kéo) thì đừng tiêu 1 ô history.
      if (samePositions(snapshot, state.positions)) return { gestureSnapshot: null }
      return {
        past: [...state.past, snapshot].slice(-MAX_HISTORY),
        future: [],
        gestureSnapshot: null,
      }
    }),

  undo: () =>
    set((state) => {
      // Không dùng `.at(-1)`: target TS của dự án chưa có Array.prototype.at.
      const previous = state.past[state.past.length - 1]
      if (previous === undefined) return {}
      return {
        positions: previous,
        past: state.past.slice(0, -1),
        future: [state.positions, ...state.future].slice(0, MAX_HISTORY),
        dirty: true,
      }
    }),

  redo: () =>
    set((state) => {
      const [next, ...rest] = state.future
      if (next === undefined) return {}
      return {
        positions: next,
        past: [...state.past, state.positions].slice(-MAX_HISTORY),
        future: rest,
        dirty: true,
      }
    }),

  markSaved: () => set({ dirty: false }),
}))
