import { create } from 'zustand'

/** Position of nodes on the canvas, by scene id. */
export type NodePositions = Record<number, { x: number; y: number }>

interface FlowState {
  positions: NodePositions
  past: NodePositions[]
  future: NodePositions[]
  /** Snapshot at the start of a drag gesture; null when not dragging. */
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
 * Store for the video-building canvas.
 *
 * Unlike `features/editor/store.ts`, undo/redo here is **grouped by gesture**: the editor
 * pushes history on every `pointermove` so one drag used up the whole 50-entry stack and undo
 * could only step back a few pixels. Here `beginGesture`/`endGesture` (wired to
 * `onNodeDragStart`/`onNodeDragStop` of React Flow) push exactly 1 entry for
 * the whole drag.
 */
export const useFlowStore = create<FlowState>()((set, get) => ({
  positions: {},
  past: [],
  future: [],
  gestureSnapshot: null,
  dirty: false,

  // Load from the server: clear history because this is a new baseline, not a user action.
  setPositions: (positions) =>
    set({ positions, past: [], future: [], gestureSnapshot: null, dirty: false }),

  moveNode: (sceneId, x, y) =>
    set((state) => ({
      positions: { ...state.positions, [sceneId]: { x, y } },
      dirty: true,
    })),

  beginGesture: () => {
    if (get().gestureSnapshot !== null) return // already in a gesture, no overlap
    set((state) => ({ gestureSnapshot: state.positions }))
  },

  endGesture: () =>
    set((state) => {
      const snapshot = state.gestureSnapshot
      if (snapshot === null) return {}
      // A click (no drag) should not spend 1 history slot.
      if (samePositions(snapshot, state.positions)) return { gestureSnapshot: null }
      return {
        past: [...state.past, snapshot].slice(-MAX_HISTORY),
        future: [],
        gestureSnapshot: null,
      }
    }),

  undo: () =>
    set((state) => {
      // Do not use `.at(-1)`: the project's TS target does not have Array.prototype.at yet.
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
