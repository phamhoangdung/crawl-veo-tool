import { useQuery } from '@tanstack/react-query'
import { getFollowedCategories } from '@/lib/api'
import { FOLLOWED_CATEGORIES_QUERY_KEY } from '@/lib/query-keys'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { AppHeader } from '@/components/layout/app-header'
import { Main } from '@/components/layout/main'
import { TopicsPanel } from '@/features/topics'
import { CategoryChart } from './category-chart'

/**
 * Trend report (Phase 20) — previously the "Topics of interest" chart
 * sat blocking the very top of the Discovery screen (~410px, pushing the whole video grid below the
 * screen), now split into its own page opened only when needed. It also merges "Topics of
 * interest" (previously a separate `/topics` page) because it is the same "look to decide
 * what to make" in nature.
 */
export function Insights() {
  const { data: followedRids } = useQuery({
    queryKey: FOLLOWED_CATEGORIES_QUERY_KEY,
    queryFn: getFollowedCategories,
  })

  return (
    <>
      <AppHeader />

      <Main>
        <div className='mb-4'>
          <h1 className='text-2xl font-bold tracking-tight'>
            Báo cáo xu hướng
          </h1>
          <p className='text-muted-foreground'>
            Chuyên mục nào đang lên, chủ đề nào đáng khai thác — dữ liệu để
            quyết định tìm gì tiếp theo, không phải để lướt liên tục.
          </p>
        </div>

        <Tabs defaultValue='categories'>
          <TabsList>
            <TabsTrigger value='categories'>Chuyên mục</TabsTrigger>
            <TabsTrigger value='topics'>Chủ đề quan tâm</TabsTrigger>
          </TabsList>
          <TabsContent value='categories' className='mt-4'>
            <CategoryChart rids={followedRids ?? []} />
          </TabsContent>
          <TabsContent value='topics' className='mt-4'>
            <TopicsPanel />
          </TabsContent>
        </Tabs>
      </Main>
    </>
  )
}
