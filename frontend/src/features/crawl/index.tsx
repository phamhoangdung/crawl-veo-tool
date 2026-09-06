import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { createCrawlJob, type JobWithVideosRead } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
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

export function Crawl() {
  const [keyword, setKeyword] = useState('')
  const [job, setJob] = useState<JobWithVideosRead | null>(null)

  const mutation = useMutation({
    mutationFn: (kw: string) => createCrawlJob(kw),
    onSuccess: (data) => setJob(data),
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
          <h1 className='text-2xl font-bold tracking-tight'>Crawl</h1>
          <p className='text-muted-foreground'>
            Nhập từ khoá để tìm và tải video từ Bilibili.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Tạo job crawl</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className='flex gap-2'
              onSubmit={(e) => {
                e.preventDefault()
                if (keyword.trim()) mutation.mutate(keyword.trim())
              }}
            >
              <Input
                placeholder='Nhập từ khoá, vd: ẩm thực'
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                disabled={mutation.isPending}
              />
              <Button type='submit' disabled={mutation.isPending || !keyword.trim()}>
                {mutation.isPending ? 'Đang tìm...' : 'Crawl'}
              </Button>
            </form>
            {mutation.isError && (
              <p className='mt-2 text-sm text-destructive'>
                Có lỗi khi crawl: {(mutation.error as Error).message}
              </p>
            )}
          </CardContent>
        </Card>

        {job && (
          <Card className='mt-4'>
            <CardHeader>
              <CardTitle>
                Kết quả cho &quot;{job.keyword}&quot; ({job.videos.length} video)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tiêu đề</TableHead>
                    <TableHead>Tác giả</TableHead>
                    <TableHead>Thời lượng</TableHead>
                    <TableHead>Trạng thái</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {job.videos.map((video) => (
                    <TableRow key={video.id}>
                      <TableCell>
                        <a
                          href={video.source_url}
                          target='_blank'
                          rel='noreferrer'
                          className='hover:underline'
                        >
                          {video.title}
                        </a>
                      </TableCell>
                      <TableCell>{video.author_name ?? '—'}</TableCell>
                      <TableCell>{formatDuration(video.duration_seconds)}</TableCell>
                      <TableCell>
                        <Badge variant='outline'>{video.status}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </Main>
    </>
  )
}
