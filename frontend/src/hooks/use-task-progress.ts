import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { API_BASE_URL, getTaskProgress, type TaskProgress } from '@/lib/api'

export const TASKS_QUERY_KEY = ['tasks'] as const

/** Trạng thái kết nối SSE, giữ trong cache để mọi component đọc được. */
const STREAM_STATUS_KEY = ['tasks', 'stream-connected'] as const

/**
 * Mở kết nối Server-Sent Events nhận tiến độ tác vụ.
 *
 * **Chỉ gọi ở MỘT nơi** (`TaskMonitor`, vốn có mặt trên mọi trang) — mỗi lần gọi
 * là một kết nối tới server. Component khác dùng `useTaskProgress()` để đọc dữ
 * liệu.
 *
 * SSE chỉ đẩy khi dữ liệu thực sự đổi nên không tốn request như polling. Khi kết
 * nối lỗi (backend chưa chạy, proxy chặn stream...), `useTaskProgress` tự quay
 * về polling để không mất theo dõi tiến độ.
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

        // Ghi thẳng vào cache: mọi component đọc key này đều cập nhật theo.
        queryClient.setQueryData(TASKS_QUERY_KEY, tasks)

        // Tác vụ chạy nền nên khi nó xong, dữ liệu trong DB đã đổi mà cache của
        // frontend thì chưa. Không làm mới ở đây thì UI vẫn thấy transcript cũ
        // và nút bước tiếp theo tiếp tục bị khoá.
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
        // Gói tin hỏng thì bỏ qua; gói kế tiếp mang trạng thái đầy đủ.
      }
    }

    source.onerror = () => {
      // EventSource tự kết nối lại; đánh dấu mất kết nối để polling đỡ lưng.
      queryClient.setQueryData(STREAM_STATUS_KEY, false)
    }

    return () => {
      source.close()
      queryClient.setQueryData(STREAM_STATUS_KEY, false)
    }
  }, [queryClient])
}

/** SSE có đang nhận dữ liệu không — dùng để quyết định có cần poll dự phòng. */
export function useStreamConnected() {
  const { data } = useQuery({
    queryKey: STREAM_STATUS_KEY,
    queryFn: () => false,
    // Giá trị do stream ghi vào, không bao giờ fetch.
    enabled: false,
    initialData: false,
  })
  return data
}

/**
 * Đọc tiến độ tác vụ. Dữ liệu do `useTaskProgressStream` đẩy vào cache; polling
 * chỉ chạy khi SSE mất kết nối.
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
