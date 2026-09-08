import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from 'vitest-browser-react'
import { describe, expect, it, vi } from 'vitest'
import '@/styles/index.css'
import type { TaskProgress } from '@/lib/api'
import { TASKS_QUERY_KEY, useVideoTaskProgress } from './use-task-progress'

vi.mock('@/lib/api', async (orig) => ({
  ...(await orig<typeof import('@/lib/api')>()),
  getTaskProgress: vi.fn(async () => []),
}))

function task(overrides: Partial<TaskProgress> = {}): TaskProgress {
  return {
    video_id: 1,
    title: 'video',
    kind: 'download',
    kind_label: 'Tải video',
    stage: 'downloading',
    stage_label: 'Đang tải',
    percent: 42,
    current: 42,
    total: 100,
    is_running: true,
    speed_per_sec: 0,
    error: null,
    ...overrides,
  }
}

function Probe({ videoId }: { videoId: number }) {
  const t = useVideoTaskProgress(videoId, 'download')
  return <span data-testid='out'>{t ? `${t.percent}|${t.is_running}` : 'null'}</span>
}

async function renderWith(tasks: TaskProgress[], videoId = 1) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(TASKS_QUERY_KEY, tasks)
  client.setQueryData(['tasks', 'stream-connected'], true)
  return await render(
    <QueryClientProvider client={client}>
      <Probe videoId={videoId} />
    </QueryClientProvider>
  )
}

describe('useVideoTaskProgress', () => {
  it('lấy đúng tiến độ của video được hỏi', async () => {
    await renderWith([task({ video_id: 9, percent: 10 }), task({ video_id: 1, percent: 77 })])

    await expect.element(document.querySelector('[data-testid=out]')!).toHaveTextContent(
      '77|true'
    )
  })

  it('trả null khi video không có tác vụ nào', async () => {
    await renderWith([task({ video_id: 9 })])

    await expect
      .element(document.querySelector('[data-testid=out]')!)
      .toHaveTextContent('null')
  })

  it('lọc theo loại tác vụ, không lấy lẫn bước khác', async () => {
    await renderWith([task({ kind: 'transcribe', percent: 5 }), task({ kind: 'download', percent: 88 })])

    await expect
      .element(document.querySelector('[data-testid=out]')!)
      .toHaveTextContent('88|true')
  })

  it('thấy được khi tác vụ đã xong', async () => {
    await renderWith([task({ is_running: false, percent: 100 })])

    // Đây là tín hiệu để dòng trong bảng đổi trạng thái khỏi "downloading".
    await expect
      .element(document.querySelector('[data-testid=out]')!)
      .toHaveTextContent('100|false')
  })
})
