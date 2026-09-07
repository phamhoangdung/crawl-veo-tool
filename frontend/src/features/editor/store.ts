import { create } from 'zustand'
import type { TimelineClip, TimelineOperations } from '@/lib/api'

export interface Selection {
  trackIndex: number
  clipIndex: number
}

interface EditorStore {
  operations: TimelineOperations
  selected: Selection | null
  setOperations: (operations: TimelineOperations) => void
  updateClip: (trackIndex: number, clipIndex: number, patch: Partial<TimelineClip>) => void
  removeClip: (trackIndex: number, clipIndex: number) => void
  select: (selection: Selection) => void
  clearSelection: () => void
}

export const useEditorStore = create<EditorStore>((set) => ({
  operations: { tracks: [] },
  selected: null,

  setOperations: (operations) => set({ operations, selected: null }),

  updateClip: (trackIndex, clipIndex, patch) =>
    set((state) => ({
      operations: {
        tracks: state.operations.tracks.map((track, tIdx) =>
          tIdx !== trackIndex
            ? track
            : {
                ...track,
                clips: track.clips.map((clip, cIdx) =>
                  cIdx !== clipIndex ? clip : { ...clip, ...patch }
                ),
              }
        ),
      },
    })),

  removeClip: (trackIndex, clipIndex) =>
    set((state) => ({
      operations: {
        tracks: state.operations.tracks.map((track, tIdx) =>
          tIdx !== trackIndex
            ? track
            : { ...track, clips: track.clips.filter((_, cIdx) => cIdx !== clipIndex) }
        ),
      },
      selected: null,
    })),

  select: (selection) => set({ selected: selection }),
  clearSelection: () => set({ selected: null }),
}))
