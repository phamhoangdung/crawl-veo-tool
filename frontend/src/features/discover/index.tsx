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
  type RankingDays,
  refreshCategories,
  searchBilibili,
  setFollowedCategories,
} from '@/lib/api'
import {
  CATEGORIES_QUERY_KEY,
  FOLLOWED_CATEGORIES_QUERY_KEY,
} from '@/lib/query-keys'
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
 * Discovery screen (Phase 20) — merges "Trends" + "Find & download" into 1 screen.
 *
 * Previously 2 separate pages: Trending only viewed/ticked and then "added to the
 * queue" (no screen could show it again, see
 * docs/phases/phase-20-discovery-workspace.md, Survey point 1), while Crawl
 * really downloaded but wrote to the DB right at search time (the origin of the bug "searching
 * a second time returns 0 videos" in phase-1). Now 1 single grid: empty search box = view the
 * ranking, with a keyword = free search, and every card can be downloaded right in place.
 */
export function Discover() {
  const queryClient = useQueryClient()
  const [platform, setPlatform] = useState<'bilibili' | 'youtube' | 'douyin'>(
    'bilibili'
  )
  const [searchInput, setSearchInput] = useState('')
  const [activeSearch, setActiveSearch] = useState('')
  const [translateKeyword, setTranslateKeyword] = useState(true)
  const [tab, setTab] = useState('all')
  const [rankingDays, setRankingDays] = useState<RankingDays>(3)

  // Categories not yet translated (name === name_zh) are translated in the BACKGROUND by the backend on every
  // call to GET /categories — poll lightly while untranslated entries remain so the Vietnamese
  // names appear gradually by themselves, with no need to click "Scan categories" again.
  const { data: categories } = useQuery({
    queryKey: CATEGORIES_QUERY_KEY,
    queryFn: getTrendingCategories,
    refetchInterval: (query) => {
      const pending =
        query.state.data?.some((c) => c.name === c.name_zh) ?? false
      return pending ? 8000 : false
    },
  })

  // The selection is stored in the DB (not localStorage) to survive packaging
  // as a desktop app and opening from another machine.
  const { data: followedRids } = useQuery({
    queryKey: FOLLOWED_CATEGORIES_QUERY_KEY,
    queryFn: getFollowedCategories,
  })

  const saveFollowed = useMutation({
    mutationFn: setFollowedCategories,
    onSuccess: (rids) => {
      queryClient.setQueryData(FOLLOWED_CATEGORIES_QUERY_KEY, rids)
    },
    onError: () => toast.error('Không lưu được lựa chọn chuyên mục.'),
  })

  const refresh = useMutation({
    mutationFn: refreshCategories,
    onSuccess: (all) => {
      queryClient.setQueryData(CATEGORIES_QUERY_KEY, all)
      toast.success(`Đã cập nhật ${all.length} chuyên mục từ Bilibili.`)
    },
    onError: () => toast.error('Không quét được chuyên mục mới.'),
  })

  const selectedRids = followedRids ?? []
  const activeCategories =
    categories?.filter((c) => selectedRids.includes(c.rid)) ?? []
  // The selected tab may disappear (unfollowing a category) — fall back to "All".
  const activeTab =
    tab === 'all' ||
    tab === 'followed-channels' ||
    activeCategories.some((c) => String(c.rid) === tab)
      ? tab
      : 'all'
  const isCategoryTab = activeTab !== 'all' && activeTab !== 'followed-channels'

  return (
    <>
      <AppHeader />

      <Main>
        <div className='mb-4 flex flex-wrap items-start justify-between gap-3'>
          <div>
            <h1 className='text-2xl font-bold tracking-tight'>
              Khám phá video
            </h1>
            <p className='text-muted-foreground'>
              Xem xu hướng, tìm theo từ khoá và tải video — tất cả trong 1 màn
              hình.
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
                  {refresh.isPending && (
                    <Loader2 className='size-3.5 animate-spin' />
                  )}
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
            {/* The trend report (category chart + topics of interest) moved
                to a secondary page, only opened when needed — previously the chart took ~410px
                at the top of the screen, pushing the whole video grid below the screen so you had to scroll
                to see it. */}
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
                  Kết quả tìm kiếm cho &quot;{activeSearch}&quot; — không phải
                  bảng xếp hạng, có thể lẫn video không liên quan.
                </p>
                <VideoGridPanel
                  queryKey={[
                    'trending',
                    'bilibili',
                    'search',
                    activeSearch,
                    translateKeyword,
                  ]}
                  fetchPage={(page) =>
                    searchBilibili(activeSearch, page, { translateKeyword })
                  }
                />
              </div>
            ) : (
              <Tabs value={activeTab} onValueChange={setTab}>
                <div className='flex flex-wrap items-center justify-between gap-2'>
                  <div className='overflow-x-auto'>
                    <TabsList>
                      <TabsTrigger value='all'>Tất cả</TabsTrigger>
                      {activeCategories.map((category) => (
                        <TabsTrigger
                          key={category.rid}
                          value={String(category.rid)}
                        >
                          {category.name}
                        </TabsTrigger>
                      ))}
                      {/* Phase 22 — decision made: 1 filter chip in the category
                        chip row, no separate navigation entry added. */}
                      <TabsTrigger value='followed-channels'>
                        Kênh đã theo dõi
                      </TabsTrigger>
                    </TabsList>
                  </div>
                  {isCategoryTab && (
                    <div className='flex items-center gap-2 text-sm'>
                      <span className='text-muted-foreground'>
                        Bảng xếp hạng:
                      </span>
                      <div className='flex gap-1 rounded-lg border bg-muted/50 p-1'>
                        {([3, 7] as const).map((d) => (
                          <Button
                            key={d}
                            type='button'
                            size='sm'
                            variant={rankingDays === d ? 'default' : 'ghost'}
                            onClick={() => setRankingDays(d)}
                          >
                            {d} ngày
                          </Button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                <TabsContent value='all' className='mt-4'>
                  <VideoGridPanel
                    queryKey={['trending', 'bilibili', 'popular-page']}
                    fetchPage={getPopularPage}
                  />
                </TabsContent>
                {activeCategories.map((category) => (
                  <TabsContent
                    key={category.rid}
                    value={String(category.rid)}
                    className='mt-4'
                  >
                    <VideoGridPanel
                      queryKey={[
                        'trending',
                        'bilibili',
                        'category-page',
                        category.rid,
                        rankingDays,
                      ]}
                      fetchPage={(page) =>
                        getCategoryPage(category.rid, page, rankingDays)
                      }
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
