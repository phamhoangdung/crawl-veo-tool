import { useQuery } from '@tanstack/react-query'
import { getTrendingCategories, getTrendingRanking } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'

function formatDuration(seconds: number | null) {
  if (seconds === null) return '—'
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes}:${rest.toString().padStart(2, '0')}`
}

function CategoryPanel({ rid }: { rid: number }) {
  const { data: videos, isLoading } = useQuery({
    queryKey: ['trending', 'bilibili', 'ranking', rid],
    queryFn: () => getTrendingRanking(rid),
  })

  if (isLoading) return <p className='text-muted-foreground'>Đang tải...</p>

  return (
    <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
      {videos?.map((video) => (
        <Card key={video.bvid}>
          {video.cover_url && (
            <img
              src={video.cover_url}
              alt=''
              className='aspect-video w-full rounded-t-xl object-cover'
            />
          )}
          <CardHeader>
            <CardTitle className='line-clamp-2 text-sm'>{video.title}</CardTitle>
          </CardHeader>
          <CardContent className='flex items-center justify-between text-xs text-muted-foreground'>
            <span>{video.author_name ?? '—'}</span>
            <span>{formatDuration(video.duration_seconds)}</span>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

export function Trending() {
  const { data: categories } = useQuery({
    queryKey: ['trending', 'bilibili', 'categories'],
    queryFn: getTrendingCategories,
  })

  return (
    <>
      <Header>
        <Search />
        <div className='ms-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ConfigDrawer />
          <ProfileDropdown />
        </div>
      </Header>

      <Main>
        <div className='mb-4'>
          <h1 className='text-2xl font-bold tracking-tight'>Trending</h1>
          <p className='text-muted-foreground'>
            Video đang hot trên Bilibili theo từng chuyên mục — dùng để chọn từ khoá crawl.
          </p>
        </div>

        {categories && categories.length > 0 && (
          <Tabs defaultValue={String(categories[0].rid)}>
            <TabsList>
              {categories.map((category) => (
                <TabsTrigger key={category.rid} value={String(category.rid)}>
                  {category.name}
                </TabsTrigger>
              ))}
            </TabsList>
            {categories.map((category) => (
              <TabsContent key={category.rid} value={String(category.rid)} className='mt-4'>
                <CategoryPanel rid={category.rid} />
              </TabsContent>
            ))}
          </Tabs>
        )}
      </Main>
    </>
  )
}
