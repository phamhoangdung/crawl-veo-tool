import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { ArrowRight, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  getCategoryPage,
  getFollowedCategories,
  getPopularPage,
  getTrendingCategories,
  refreshCategories,
  searchBilibili,
  setFollowedCategories,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { KeywordSearchBox } from '@/components/keyword-search-box'
import { AppHeader } from '@/components/layout/app-header'
import { Main } from '@/components/layout/main'
import { CategoryPicker } from './category-picker'
import { DouyinPanel } from './douyin-panel'
import { FollowedChannelsPanel } from './followed-channels-panel'
import { VideoGridPanel } from './video-grid-panel'
import { YoutubePanel } from './youtube-panel'

/**
 * Màn Khám phá (Phase 20) — gộp "Xu hướng" + "Tìm & tải" thành 1 màn hình.
 *
 * Trước đây 2 trang tách rời: Trending chỉ xem/tick chọn rồi "thêm vào hàng
 * đợi" (không màn hình nào hiển thị lại được, xem
 * docs/phases/phase-20-discovery-workspace.md mục Khảo sát điểm 1), Crawl
 * mới thực sự tải được nhưng lại ghi DB ngay lúc search (nguồn gốc bug "tìm
 * lần 2 ra 0 video" ở phase-1). Giờ 1 lưới duy nhất: trống ô tìm = xem xếp
 * hạng, có từ khoá = tìm tự do, mọi thẻ đều tải được ngay tại chỗ.
 */
export function Discover() {
  const queryClient = useQueryClient()
  const [platform, setPlatform] = useState<'bilibili' | 'youtube' | 'douyin'>('bilibili')
  const [searchInput, setSearchInput] = useState('')
  const [activeSearch, setActiveSearch] = useState('')
  const [translateKeyword, setTranslateKeyword] = useState(true)

  // Chuyên mục chưa dịch (name === name_zh) được backend tự dịch NỀN mỗi lần
  // gọi GET /categories — poll nhẹ trong lúc còn mục chưa dịch để tên tiếng
  // Việt tự hiện ra dần, không cần bấm lại "Quét chuyên mục".
  const { data: categories } = useQuery({
    queryKey: ['trending', 'bilibili', 'categories'],
    queryFn: getTrendingCategories,
    refetchInterval: (query) => {
      const pending = query.state.data?.some((c) => c.name === c.name_zh) ?? false
      return pending ? 8000 : false
    },
  })

  // Lựa chọn lưu ở DB (không phải localStorage) để giữ nguyên khi đóng gói
  // thành app desktop và khi mở từ máy khác.
  const { data: followedRids } = useQuery({
    queryKey: ['trending', 'bilibili', 'followed'],
    queryFn: getFollowedCategories,
  })

  const saveFollowed = useMutation({
    mutationFn: setFollowedCategories,
    onSuccess: (rids) => {
      queryClient.setQueryData(['trending', 'bilibili', 'followed'], rids)
    },
    onError: () => toast.error('Không lưu được lựa chọn chuyên mục.'),
  })

  const refresh = useMutation({
    mutationFn: refreshCategories,
    onSuccess: (all) => {
      queryClient.setQueryData(['trending', 'bilibili', 'categories'], all)
      toast.success(`Đã cập nhật ${all.length} chuyên mục từ Bilibili.`)
    },
    onError: () => toast.error('Không quét được chuyên mục mới.'),
  })

  const selectedRids = followedRids ?? []
  const activeCategories = categories?.filter((c) => selectedRids.includes(c.rid)) ?? []

  return (
    <>
      <AppHeader />

      <Main>
        <div className='mb-4 flex flex-wrap items-start justify-between gap-3'>
          <div>
            <h1 className='text-2xl font-bold tracking-tight'>Khám phá video</h1>
            <p className='text-muted-foreground'>
              Xem xu hướng, tìm theo từ khoá và tải video — tất cả trong 1 màn hình.
            </p>
          </div>
          <div className='flex items-center gap-2'>
            {platform === 'bilibili' && (
              <>
                <Button
                  variant='ghost'
                  size='sm'
                  disabled={refresh.isPending}
                  onClick={() => refresh.mutate()}
                >
                  {refresh.isPending && <Loader2 className='size-3.5 animate-spin' />}
                  {refresh.isPending ? 'Đang quét...' : 'Quét chuyên mục mới'}
                </Button>
                {categories && (
                  <CategoryPicker
                    categories={categories}
                    selected={selectedRids}
                    onChange={(rids) => saveFollowed.mutate(rids)}
                  />
                )}
              </>
            )}
            {/* Báo cáo xu hướng (biểu đồ chuyên mục + chủ đề quan tâm) chuyển
                sang trang phụ, chỉ mở khi cần — trước đây biểu đồ chiếm ~410px
                đầu màn hình, đẩy cả lưới video xuống dưới màn hình phải cuộn
                mới thấy. */}
            <Button asChild variant='outline' size='sm'>
              <Link to='/insights'>
                Báo cáo xu hướng
                <ArrowRight className='size-3.5' />
              </Link>
            </Button>
          </div>
        </div>

        <div className='mb-4 flex w-fit gap-1 rounded-lg border bg-muted/50 p-1'>
          <Button
            type='button'
            size='sm'
            variant={platform === 'bilibili' ? 'default' : 'ghost'}
            onClick={() => setPlatform('bilibili')}
          >
            Bilibili
          </Button>
          <Button
            type='button'
            size='sm'
            variant={platform === 'youtube' ? 'default' : 'ghost'}
            onClick={() => setPlatform('youtube')}
          >
            YouTube
          </Button>
          <Button
            type='button'
            size='sm'
            variant={platform === 'douyin' ? 'default' : 'ghost'}
            onClick={() => setPlatform('douyin')}
          >
            Douyin
          </Button>
        </div>

        {platform === 'youtube' && <YoutubePanel />}
        {platform === 'douyin' && <DouyinPanel />}

        {platform === 'bilibili' && (
          <>
            <KeywordSearchBox
              className='mb-4'
              inputClassName='max-w-md'
              value={searchInput}
              onChange={setSearchInput}
              onSubmit={() => setActiveSearch(searchInput.trim())}
              placeholder='Tìm video theo từ khoá bất kỳ, không giới hạn chuyên mục...'
              translateKeyword={translateKeyword}
              onTranslateKeywordChange={setTranslateKeyword}
              onClear={
                activeSearch
                  ? () => {
                      setActiveSearch('')
                      setSearchInput('')
                    }
                  : undefined
              }
            />

            {activeSearch ? (
              <div className='space-y-4'>
                <p className='text-sm text-muted-foreground'>
                  Kết quả tìm kiếm cho &quot;{activeSearch}&quot; — không phải bảng
                  xếp hạng, có thể lẫn video không liên quan.
                </p>
                <VideoGridPanel
                  queryKey={['trending', 'bilibili', 'search', activeSearch, translateKeyword]}
                  fetchPage={(page) =>
                    searchBilibili(activeSearch, page, { translateKeyword })
                  }
                />
              </div>
            ) : (
              <Tabs defaultValue='all'>
                <div className='overflow-x-auto'>
                  <TabsList>
                    <TabsTrigger value='all'>Tất cả</TabsTrigger>
                    {activeCategories.map((category) => (
                      <TabsTrigger key={category.rid} value={String(category.rid)}>
                        {category.name}
                      </TabsTrigger>
                    ))}
                    {/* Phase 22 — quyết định đã chốt: 1 chip lọc trong hàng chip
                        chuyên mục, không thêm mục điều hướng riêng. */}
                    <TabsTrigger value='followed-channels'>Kênh đã theo dõi</TabsTrigger>
                  </TabsList>
                </div>
                <TabsContent value='all' className='mt-4'>
                  <VideoGridPanel
                    queryKey={['trending', 'bilibili', 'popular-page']}
                    fetchPage={getPopularPage}
                  />
                </TabsContent>
                {activeCategories.map((category) => (
                  <TabsContent key={category.rid} value={String(category.rid)} className='mt-4'>
                    <VideoGridPanel
                      queryKey={['trending', 'bilibili', 'category-page', category.rid]}
                      fetchPage={(page) => getCategoryPage(category.rid, page)}
                    />
                  </TabsContent>
                ))}
                <TabsContent value='followed-channels' className='mt-4'>
                  <FollowedChannelsPanel />
                </TabsContent>
              </Tabs>
            )}
          </>
        )}
      </Main>
    </>
  )
}
