import { useQuery } from '@tanstack/react-query'
import { getFollowedCategories } from '@/lib/api'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { AppHeader } from '@/components/layout/app-header'
import { Main } from '@/components/layout/main'
import { TopicsPanel } from '@/features/topics'
import { CategoryChart } from './category-chart'

/**
 * Báo cáo xu hướng (Phase 20) — trước đây biểu đồ "Chủ đề đang được quan
 * tâm" nằm chắn ngay đầu màn Khám phá (~410px, đẩy cả lưới video xuống dưới
 * màn hình), giờ tách thành trang riêng chỉ mở khi cần. Gộp luôn "Chủ đề
 * quan tâm" (trước là trang `/topics` riêng) vì cùng bản chất "xem để quyết
 * định làm gì".
 */
export function Insights() {
  const { data: followedRids } = useQuery({
    queryKey: ['trending', 'bilibili', 'followed'],
    queryFn: getFollowedCategories,
  })

  return (
    <>
      <AppHeader />

      <Main>
        <div className='mb-4'>
          <h1 className='text-2xl font-bold tracking-tight'>Báo cáo xu hướng</h1>
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
