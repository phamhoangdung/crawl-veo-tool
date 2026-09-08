import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from 'vitest-browser-react'
import { describe, expect, it, vi } from 'vitest'
import '@/styles/index.css'
import type { TaskProgress, VideoRead } from '@/lib/api'
import { TASKS_QUERY_KEY } from '@/hooks/use-task-progress'
import { VideoRow } from './index'

// Mock router: VideoRow chỉ dùng <Link>, nhưng module khác trong cây import
// cũng cần các export này.
vi.mock('@tanstack/react-router', async (orig) => ({
  ...(await orig<typeof import('@tanstack/react-router')>()),
  Link: ({ children }: { children?: React.ReactNode }) => <a>{children}</a>,
}))

function video(overrides: Partial<VideoRead> = {}): VideoRead {
  return {
    id: 1,
    platform: 'bilibili',
    platform_video_id: 'BV1',
    title: '世界匹克球头号选手BenJohns 单打集锦',
    source_url: 'https://bilibili.com/BV1',
    cover_url: null,
    author_name: '天天匹克球',
    duration_seconds: 25,
    status: 'downloading',
    ...overrides,
  } as VideoRead
}

function task(overrides: Partial<TaskProgress> = {}): TaskProgress {
  return {
    video_id: 1,
    title: 'v',
    kind: 'download',
    kind_label: 'Tải video',
    stage: 'downloading',
    stage_label: 'Đang tải',
    percent: 45,
    current: 45,
    total: 100,
    is_running: true,
    speed_per_sec: 0,
    error: null,
    ...overrides,
  }
}

async function renderRow(tasks: TaskProgress[], v = video()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(TASKS_QUERY_KEY, tasks)
  client.setQueryData(['tasks', 'stream-connected'], true)
  const onUpdate = vi.fn()
  const screen = await render(
    <QueryClientProvider client={client}>
      <table>
        <tbody>
          <VideoRow video={v} onUpdate={onUpdate} />
        </tbody>
      </table>
    </QueryClientProvider>
  )
  return { screen, onUpdate }
}

describe('VideoRow — đồng bộ tiến độ tải', () => {
  it('hiện thanh % khi đang tải', async () => {
    await renderRow([task({ percent: 45 })])

    const bar = document.querySelector('[data-testid=download-progress-bar]') as HTMLElement
    expect(bar).not.toBeNull()
    expect(bar.style.width).toBe('45%')
    expect(document.body.textContent).toContain('45%')
  })

  it('KHÔNG hiện thanh % khi không có tác vụ chạy', async () => {
    await renderRow([], video({ status: 'queued' }))

    expect(document.querySelector('[data-testid=download-progress-bar]')).toBeNull()
  })

  it('đổi trạng thái sang downloaded khi tác vụ xong', async () => {
    // Đây chính là lỗi: panel Tác vụ báo "Hoàn tất" mà dòng vẫn "downloading".
    const { onUpdate } = await renderRow([task({ is_running: false, percent: 100 })])

    await vi.waitFor(() =>
      expect(onUpdate).toHaveBeenCalledWith(1, { status: 'downloaded' })
    )
  })

  it('đổi sang failed_download khi tác vụ lỗi', async () => {
    const { onUpdate } = await renderRow([
      task({ is_running: false, error: 'mạng lỗi' }),
    ])

    await vi.waitFor(() =>
      expect(onUpdate).toHaveBeenCalledWith(1, { status: 'failed_download' })
    )
  })

  it('chỉ báo xong MỘT lần, không gọi lặp', async () => {
    const { onUpdate } = await renderRow([task({ is_running: false, percent: 100 })])

    await vi.waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1))
    await new Promise((r) => setTimeout(r, 200))
    expect(onUpdate).toHaveBeenCalledTimes(1)
  })
})
