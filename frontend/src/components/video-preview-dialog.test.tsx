import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from 'vitest-browser-react'
import { describe, expect, it, vi } from 'vitest'
import '@/styles/index.css'
import { getChannelVideos, getRelatedVideos, setChannelFollowed, type TrendingVideo } from '@/lib/api'
import { VideoPreviewDialog } from './video-preview-dialog'

// ESM không cho spy vào export trong browser mode — phải mock ở tầng module.
vi.mock('@/lib/api', async (orig) => ({
  ...(await orig<typeof import('@/lib/api')>()),
  getRelatedVideos: vi.fn(),
  getChannelVideos: vi.fn(),
  setChannelFollowed: vi.fn(),
}))
const mockRelated = vi.mocked(getRelatedVideos)
const mockChannelVideos = vi.mocked(getChannelVideos)
const mockSetFollowed = vi.mocked(setChannelFollowed)

function suggestion(bvid: string, overrides: Partial<TrendingVideo> = {}): TrendingVideo {
  return {
    bvid,
    title: `video ${bvid}`,
    author_name: 'tác giả',
    play_count: null,
    like_count: null,
    duration_seconds: null,
    cover_url: null,
    comment_count: null,
    danmaku_count: null,
    coin_count: null,
    heat_score: null,
    published_at: null,
    video_id: null,
    already_in_library: false,
    channel_id: null,
    channel_is_followed: false,
    ...overrides,
  }
}

async function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe('VideoPreviewDialog', () => {
  it('đóng khi title=null — không hiện iframe/link', async () => {
    await wrap(
      <VideoPreviewDialog
        title={null}
        embedUrl={null}
        externalUrl={null}
        externalLabel='Mở trên Bilibili'
        onClose={() => {}}
      />
    )

    expect(document.querySelector('iframe')).toBeNull()
  })

  it('mở đúng iframe embed + link ngoài theo props truyền vào (dùng chung cho cả Bilibili lẫn YouTube)', async () => {
    await wrap(
      <VideoPreviewDialog
        title='Video test'
        embedUrl='https://player.bilibili.com/player.html?bvid=BV123'
        externalUrl='https://www.bilibili.com/video/BV123'
        externalLabel='Mở trên Bilibili'
        onClose={() => {}}
      />
    )

    const iframe = document.querySelector('iframe') as HTMLIFrameElement
    expect(iframe.src).toBe('https://player.bilibili.com/player.html?bvid=BV123')

    const link = document.querySelector('a[href*="bilibili.com"]') as HTMLAnchorElement
    expect(link.href).toBe('https://www.bilibili.com/video/BV123')
    expect(link.textContent).toContain('Mở trên Bilibili')
    expect(document.body.textContent).toContain('Video test')
  })

  it('gọi onClose khi đóng dialog', async () => {
    const onClose = vi.fn()
    const screen = await wrap(
      <VideoPreviewDialog
        title='Video test'
        embedUrl='https://www.youtube.com/embed/abc'
        externalUrl='https://www.youtube.com/watch?v=abc'
        externalLabel='Mở trên YouTube'
        onClose={onClose}
      />
    )

    // Radix Dialog: nút đóng mặc định có aria-label "Close".
    await screen.getByRole('button', { name: /close/i }).click()
    expect(onClose).toHaveBeenCalledOnce()
  })

  describe('Phase 22 — kênh + gợi ý (chỉ khi có bvid, YouTube không đụng tới)', () => {
    it('không có bvid (YouTube): không gọi API kênh/gợi ý, không hiện khối kênh', async () => {
      await wrap(
        <VideoPreviewDialog
          title='Video YouTube'
          embedUrl='https://www.youtube.com/embed/abc'
          externalUrl='https://www.youtube.com/watch?v=abc'
          externalLabel='Mở trên YouTube'
          onClose={() => {}}
        />
      )

      expect(mockRelated).not.toHaveBeenCalled()
      expect(mockChannelVideos).not.toHaveBeenCalled()
      expect(document.body.textContent).not.toContain('Video tương tự')
    })

    it('có bvid: hiện tên kênh + nút Theo dõi, gọi đúng 2 API gợi ý', async () => {
      mockRelated.mockResolvedValue({ videos: [], page: 1, has_more: false, source: 'popular' })
      mockChannelVideos.mockResolvedValue({
        videos: [],
        page: 1,
        has_more: false,
        source: 'popular',
      })

      const screen = await wrap(
        <VideoPreviewDialog
          title='Video Bilibili'
          embedUrl='https://player.bilibili.com/player.html?bvid=BV1'
          externalUrl='https://www.bilibili.com/video/BV1'
          externalLabel='Mở trên Bilibili'
          onClose={() => {}}
          bvid='BV1'
          channelId='42'
          channelName='Kênh test'
          channelIsFollowed={false}
          onSelectVideo={() => {}}
        />
      )

      await expect.element(screen.getByText('Kênh test')).toBeInTheDocument()
      await expect
        .element(screen.getByRole('button', { name: /theo dõi/i }))
        .toBeInTheDocument()

      await vi.waitFor(() => {
        expect(mockRelated).toHaveBeenCalledWith('BV1')
        expect(mockChannelVideos).toHaveBeenCalledWith('42')
      })
    })

    it('bấm nút Theo dõi gọi đúng API với channelId/tên/followed=true', async () => {
      mockRelated.mockResolvedValue({ videos: [], page: 1, has_more: false, source: 'popular' })
      mockChannelVideos.mockResolvedValue({
        videos: [],
        page: 1,
        has_more: false,
        source: 'popular',
      })
      mockSetFollowed.mockResolvedValue({
        platform: 'bilibili',
        channel_id: '42',
        name: 'Kênh test',
        avatar_url: null,
        is_followed: true,
      })

      const screen = await wrap(
        <VideoPreviewDialog
          title='Video Bilibili'
          embedUrl='https://player.bilibili.com/player.html?bvid=BV1'
          externalUrl='https://www.bilibili.com/video/BV1'
          externalLabel='Mở trên Bilibili'
          onClose={() => {}}
          bvid='BV1'
          channelId='42'
          channelName='Kênh test'
          channelIsFollowed={false}
          onSelectVideo={() => {}}
        />
      )

      await screen.getByRole('button', { name: /theo dõi/i }).click()

      await vi.waitFor(() =>
        expect(mockSetFollowed).toHaveBeenCalledWith('bilibili', '42', 'Kênh test', true)
      )
    })

    it('dải "Video khác trong kênh" bị degraded: hiện thông báo suy giảm, không phải danh sách rỗng im lặng', async () => {
      mockRelated.mockResolvedValue({ videos: [], page: 1, has_more: false, source: 'popular' })
      mockChannelVideos.mockResolvedValue({
        videos: [],
        page: 1,
        has_more: false,
        source: 'popular',
        degraded: true,
      })

      const screen = await wrap(
        <VideoPreviewDialog
          title='Video Bilibili'
          embedUrl='https://player.bilibili.com/player.html?bvid=BV1'
          externalUrl='https://www.bilibili.com/video/BV1'
          externalLabel='Mở trên Bilibili'
          onClose={() => {}}
          bvid='BV1'
          channelId='42'
          channelName='Kênh test'
          onSelectVideo={() => {}}
        />
      )

      await expect
        .element(screen.getByText(/đang giới hạn truy cập kênh/i))
        .toBeInTheDocument()
    })

    it('bấm vào 1 thẻ gợi ý gọi onSelectVideo với đúng video, KHÔNG mở dialog chồng dialog', async () => {
      const related = [suggestion('BV2', { title: 'video liên quan' })]
      mockRelated.mockResolvedValue({
        videos: related,
        page: 1,
        has_more: false,
        source: 'popular',
      })
      mockChannelVideos.mockResolvedValue({
        videos: [],
        page: 1,
        has_more: false,
        source: 'popular',
      })

      const onSelectVideo = vi.fn()
      const screen = await wrap(
        <VideoPreviewDialog
          title='Video Bilibili'
          embedUrl='https://player.bilibili.com/player.html?bvid=BV1'
          externalUrl='https://www.bilibili.com/video/BV1'
          externalLabel='Mở trên Bilibili'
          onClose={() => {}}
          bvid='BV1'
          channelId='42'
          channelName='Kênh test'
          onSelectVideo={onSelectVideo}
        />
      )

      await screen.getByText('video liên quan').click()

      expect(onSelectVideo).toHaveBeenCalledWith(related[0])
      // Vẫn chỉ đúng 1 dialog — không có dialog thứ 2 nào được mở thêm.
      expect(document.querySelectorAll('[role=dialog]').length).toBe(1)
    })
  })
})
