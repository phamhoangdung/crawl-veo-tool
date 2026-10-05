import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  API_BASE_URL,
  getTaskProgress,
  type TaskKind,
  type TaskProgress,
} from '@/lib/api'

export const TASKS_QUERY_KEY = ['tasks'] as const

/** SSE connection state, kept in the cache so every component can read it. */
const STREAM_STATUS_KEY = ['tasks', 'stream-connected'] as const

/**
 * Open a Server-Sent Events connection to receive task progress.
 *
 * **Call it in only ONE place** (`TaskMonitor`, which is present on every page) — every call
 * is a connection to the server. Other components use `useTaskProgress()` to read the
 * data.
 *
 * SSE only pushes when the data really changes so it costs no requests like polling. When the
 * connection fails (backend not running, a proxy blocking the stream...), `useTaskProgress` falls back
 * to polling by itself so progress tracking is not lost.
 */
export function useTaskProgressStream() {
  const queryClient = useQueryClient()

  useEffect(() => {
    const source = new EventSource(`${API_BASE_URL}/api/downloads/stream`)

    source.onopen = () => queryClient.setQueryData(STREAM_STATUS_KEY, true)

    source.onmessage = (event) => {
      try {
        const tasks = JSON.parse(event.data) as TaskProgress[]
        const previous =
          queryClient.getQueryData<TaskProgress[]>(TASKS_QUERY_KEY) ?? []

        // Write straight into the cache: every component reading this key updates along.
        queryClient.setQueryData(TASKS_QUERY_KEY, tasks)

        // A task runs in the background so when it finishes, the data in the DB has changed but the
        // frontend cache has not. Without refreshing here the UI would still see the old transcript
        // and the next step button would stay locked.
        for (const task of tasks) {
          const before = previous.find(
            (t) => t.video_id === task.video_id && t.kind === task.kind
          )
          const justFinished = before?.is_running === true && !task.is_running
          if (!justFinished) continue

          queryClient.invalidateQueries({ queryKey: ['video', task.video_id] })
          queryClient.invalidateQueries({ queryKey: ['files'] })
          queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
        }
      } catch {
        // A corrupt packet is skipped; the next packet carries the full state.
      }
    }

    source.onerror = () => {
      // EventSource reconnects by itself; mark the connection as lost so polling can back it up.
      queryClient.setQueryData(STREAM_STATUS_KEY, false)
    }

    return () => {
      source.close()
      queryClient.setQueryData(STREAM_STATUS_KEY, false)
    }
  }, [queryClient])
}

/** Whether SSE is receiving data — used to decide whether fallback polling is needed. */
export function useStreamConnected() {
  const { data } = useQuery({
    queryKey: STREAM_STATUS_KEY,
    queryFn: () => false,
    // A value written by the stream, never fetched.
    enabled: false,
    initialData: false,
  })
  return data
}

/**
 * Read task progress. The data is pushed into the cache by `useTaskProgressStream`; polling
 * only runs when SSE is disconnected.
 */
export function useTaskProgress() {
  const streamConnected = useStreamConnected()

  const query = useQuery({
    queryKey: TASKS_QUERY_KEY,
    queryFn: getTaskProgress,
    refetchInterval: streamConnected ? false : 1500,
    refetchOnWindowFocus: !streamConnected,
  })

  return query.data ?? []
}

/**
 * Progress of ONE video (optionally filtered by task kind) — to show the % bar right
 * on that row instead of making the user open the Tasks panel to cross-reference.
 */
export function useVideoTaskProgress(videoId: number, kind?: TaskKind) {
  const tasks = useTaskProgress()
  return (
    tasks.find((t) => t.video_id === videoId && (kind === undefined || t.kind === kind)) ?? null
  )
}
