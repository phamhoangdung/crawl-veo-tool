import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from 'vitest-browser-react'
import { describe, expect, it, vi } from 'vitest'
import '@/styles/index.css'
import type { TaskProgress, TrendingVideo } from '@/lib/api'
import { TASKS_QUERY_KEY } from '@/hooks/use-task-progress'
import { SelectedVideosCart, VideoCard } from './video-grid-panel'

// Mock router: VideoCard dùng <Link to='/videos/$videoId' params={...}> —
// nội suy `$param` giống hành vi thật để href assert được chính xác.
vi.mock('@tanstack/react-router', async (orig) => ({
  ...(await orig<typeof import('@tanstack/react-router')>()),
  Link: ({
    children,
    to,
    params,
    onClick,
  }: {
    children?: React.ReactNode
    to?: string
    params?: Record<string, string>
    onClick?: (e: React.MouseEvent) => void
  }) => {
    const href = Object.entries(params ?? {}).reduce(
      (path, [key, value]) => path.replace(`$${key}`, value),
      to ?? ''
    )
    return (
      <a href={href} onClick={onClick}>
        {children}
      </a>
    )
  },
}))

function video(overrides: Partial<TrendingVideo> = {}): TrendingVideo {
  return {
    bvid: 'BV1',
    title: '世界匹克球头号选手BenJohns 单打集锦',
    author_name: '天天匹克球',
    play_count: 1000,
    like_count: 100,
    duration_seconds: 25,
    cover_url: null,
    comment_count: 10,
    danmaku_count: 5,
    coin_count: 20,
    heat_score: null,
    published_at: null,
    video_id: null,
    already_in_library: false,
    channel_id: null,
    channel_is_followed: false,
    ...overrides,
  }
}

function task(overrides: Partial<TaskProgress> = {}): TaskProgress {
  return {
    video_id: 1,
    subject_type: 'video',
    title: 'v',
    kind: 'download',
    kind_label: 'Tải video',
    stage: 'video',
    stage_label: 'Đang tải hình',
    percent: 45,
    current: 45,
    total: 100,
    is_running: true,
    speed_per_sec: 0,
    error: null,
    ...overrides,
  }
}

async function renderCard(v: TrendingVideo, tasks: TaskProgress[] = []) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(TASKS_QUERY_KEY, tasks)
  client.setQueryData(['tasks', 'stream-connected'], true)
  return render(
    <QueryClientProvider client={client}>
      <VideoCard
        video={v}
        isPicked={false}
        onToggle={() => {}}
        onPreview={() => {}}
        onDownloadOne={() => {}}
        downloadingOne={false}
      />
    </QueryClientProvider>
  )
}

describe('VideoCard — trạng thái tải (Phase 20)', () => {
  it('chưa từng tải: hiện nút "Tải video", không hiện thanh % hay link thư viện', async () => {
    await renderCard(video({ video_id: null, already_in_library: false }))

    expect(document.body.textContent).toContain('Tải video')
    expect(document.querySelector('[data-testid=discover-download-progress-bar]')).toBeNull()
    expect(document.body.textContent).not.toContain('Đã có trong thư viện')
  })

  it('đang tải: hiện thanh % đúng theo task SSE, không hiện nút "Tải video"', async () => {
    await renderCard(
      video({ video_id: 1, already_in_library: true }),
      [task({ video_id: 1, percent: 45 })]
    )

    const bar = document.querySelector(
      '[data-testid=discover-download-progress-bar]'
    ) as HTMLElement
    expect(bar).not.toBeNull()
    expect(bar.style.width).toBe('45%')
    expect(document.body.textContent).not.toContain('Tải video')
  })

  it('đã có sẵn, không còn tác vụ chạy: hiện link sang Video của tôi', async () => {
    await renderCard(video({ video_id: 7, already_in_library: true }), [])

    expect(document.querySelector('[data-testid=discover-download-progress-bar]')).toBeNull()
    const link = document.querySelector('a[href="/videos/7"]')
    expect(link).not.toBeNull()
    expect(link!.textContent).toContain('Đã có trong thư viện')
  })
})

describe('SelectedVideosCart — phản hồi người dùng: chọn nhiều video trong lưới dài không phải cuộn lại tìm', () => {
  async function renderCart(overrides: {
    videos?: TrendingVideo[]
    onRemove?: (bvid: string) => void
    onClear?: () => void
    onDownload?: () => void
    isDownloading?: boolean
  } = {}) {
    return render(
      <SelectedVideosCart
        videos={overrides.videos ?? [video({ bvid: 'BV1' }), video({ bvid: 'BV2' })]}
        onRemove={overrides.onRemove ?? (() => {})}
        onClear={overrides.onClear ?? (() => {})}
        onDownload={overrides.onDownload ?? (() => {})}
        isDownloading={overrides.isDownloading ?? false}
      />
    )
  }

  it('hiện đúng số lượng + tiêu đề từng video đã chọn', async () => {
    await renderCart({
      videos: [video({ bvid: 'BV1', title: 'video một' }), video({ bvid: 'BV2', title: 'video hai' })],
    })

    expect(document.body.textContent).toContain('Đã chọn 2')
    expect(document.body.textContent).toContain('video một')
    expect(document.body.textContent).toContain('video hai')
  })

  it('bấm nút X ở 1 video gọi onRemove đúng bvid, không đụng video khác', async () => {
    const onRemove = vi.fn()
    const screen = await renderCart({
      videos: [video({ bvid: 'BV1', title: 'video một' }), video({ bvid: 'BV2', title: 'video hai' })],
      onRemove,
    })

    await screen.getByTitle('Bỏ chọn').first().click()

    expect(onRemove).toHaveBeenCalledOnce()
    expect(onRemove).toHaveBeenCalledWith('BV1')
  })

  it('bấm "Bỏ chọn tất cả" gọi onClear', async () => {
    const onClear = vi.fn()
    const screen = await renderCart({ onClear })

    await screen.getByText('Bỏ chọn tất cả').click()
    expect(onClear).toHaveBeenCalledOnce()
  })

  it('bấm nút tải gọi onDownload, hiện đúng số lượng trong nhãn nút', async () => {
    const onDownload = vi.fn()
    const screen = await renderCart({
      videos: [video({ bvid: 'BV1' }), video({ bvid: 'BV2' }), video({ bvid: 'BV3' })],
      onDownload,
    })

    const btn = screen.getByRole('button', { name: /Tải 3 video đã chọn/ })
    await expect.element(btn).toBeInTheDocument()
    await btn.click()
    expect(onDownload).toHaveBeenCalledOnce()
  })

  it('isDownloading=true: nút tải bị disable, không gọi được onDownload', async () => {
    const onDownload = vi.fn()
    const screen = await renderCart({ isDownloading: true, onDownload })

    const btn = screen.getByRole('button', { name: /Đang thêm/ })
    await expect.element(btn).toBeDisabled()
  })
})
