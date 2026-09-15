import { useState } from 'react'
import axios from 'axios'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, Flame, Gauge, Loader2, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  computeTopicScore,
  createTopic,
  deleteTopic,
  getTopics,
  getYoutubeStatus,
  type Topic,
} from '@/lib/api'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { TaskMonitor } from '@/components/task-monitor'
import { ThemeSwitch } from '@/components/theme-switch'

function axiosDetail(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) return fallback
  const detail = (error.response?.data as { detail?: string })?.detail
  return detail ?? fallback
}

/** Nhãn định tính cho điểm cơ hội (trung vị tỉ lệ view/sub kênh) — heuristic
 * tham khảo, không phải điểm số khoa học chính xác (xem docstring backend
 * `topic_service.py`). Ngưỡng chọn theo kinh nghiệm phổ biến khi soi "video
 * outlier" trên YouTube: 1 video ăn khách gấp 20 lần quy mô kênh trở lên là
 * hiếm và đáng chú ý. */
function scoreBadge(score: number | null) {
  if (score === null) return null
  if (score >= 20) {
    return { label: 'Cơ hội cao', className: 'bg-green-500/15 text-green-600' }
  }
  if (score >= 5) {
    return {
      label: 'Trung bình',
      className: 'bg-yellow-500/15 text-yellow-700',
    }
  }
  return { label: 'Thấp', className: 'bg-muted text-muted-foreground' }
}

function TopicCard({ topic }: { topic: Topic }) {
  const queryClient = useQueryClient()
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['topics'] })

  const score = useMutation({
    mutationFn: () => computeTopicScore(topic.id),
    onSuccess: invalidate,
    onError: (error) =>
      toast.error(axiosDetail(error, 'Không tính được điểm chủ đề.')),
  })

  const remove = useMutation({
    mutationFn: () => deleteTopic(topic.id),
    onSuccess: invalidate,
    onError: () => toast.error('Không xoá được chủ đề.'),
  })

  const badge = scoreBadge(topic.score)

  return (
    <Card>
      <CardHeader className='flex flex-row items-start justify-between gap-2 space-y-0'>
        <div>
          <CardTitle className='text-base'>{topic.name}</CardTitle>
          {topic.query !== topic.name && (
            <p className='mt-1 text-xs text-muted-foreground'>
              Từ khoá tìm: {topic.query}
            </p>
          )}
        </div>
        <Button
          type='button'
          size='icon'
          variant='ghost'
          className='shrink-0 text-muted-foreground hover:text-destructive'
          onClick={() => remove.mutate()}
          disabled={remove.isPending}
          title='Xoá chủ đề'
        >
          {remove.isPending ? (
            <Loader2 className='size-4 animate-spin' />
          ) : (
            <Trash2 className='size-4' />
          )}
        </Button>
      </CardHeader>
      <CardContent className='space-y-3'>
        {topic.note && (
          <p className='text-sm text-muted-foreground'>{topic.note}</p>
        )}

        {badge ? (
          <div className='space-y-2'>
            <div className='flex flex-wrap items-center gap-2'>
              <span
                className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}
              >
                <Flame className='size-3' />
                {badge.label}
              </span>
              <span className='text-xs text-muted-foreground'>
                Tỉ lệ view/sub trung vị: {topic.score?.toFixed(1)}x · mẫu{' '}
                {topic.sample_video_count} video · {topic.competition_count}{' '}
                video cạnh tranh trong 30 ngày
              </span>
            </div>
            {topic.top_video_title && topic.top_video_url && (
              <a
                href={topic.top_video_url}
                target='_blank'
                rel='noopener noreferrer'
                className='flex items-center gap-1 text-xs text-primary hover:underline'
              >
                <ExternalLink className='size-3' />
                Video tiêu biểu: {topic.top_video_title}
              </a>
            )}
          </div>
        ) : (
          <p className='text-xs text-muted-foreground'>
            Chưa tính điểm cơ hội.
          </p>
        )}

        <Button
          type='button'
          size='sm'
          variant='outline'
          onClick={() => score.mutate()}
          disabled={score.isPending}
        >
          {score.isPending ? (
            <Loader2 className='size-3.5 animate-spin' />
          ) : (
            <Gauge className='size-3.5' />
          )}
          {topic.score === null ? 'Tính điểm cơ hội' : 'Tính lại'}
        </Button>
      </CardContent>
    </Card>
  )
}

export function Topics() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [query, setQuery] = useState('')
  const [note, setNote] = useState('')

  const youtubeStatus = useQuery({
    queryKey: ['youtube', 'status'],
    queryFn: getYoutubeStatus,
  })

  const topics = useQuery({
    queryKey: ['topics'],
    queryFn: getTopics,
  })

  const create = useMutation({
    mutationFn: () =>
      createTopic({
        name: name.trim(),
        query: query.trim() || undefined,
        note: note.trim() || undefined,
      }),
    onSuccess: () => {
      setName('')
      setQuery('')
      setNote('')
      queryClient.invalidateQueries({ queryKey: ['topics'] })
    },
    onError: () => toast.error('Không thêm được chủ đề.'),
  })

  return (
    <>
      <Header>
        <Search />
        <div className='ms-auto flex items-center space-x-4'>
          <TaskMonitor />
          <ThemeSwitch />
          <ConfigDrawer />
          <ProfileDropdown />
        </div>
      </Header>

      <Main>
        <div className='mb-4'>
          <h1 className='text-2xl font-bold tracking-tight'>Chủ đề quan tâm</h1>
          <p className='text-muted-foreground'>
            Lưu các chủ đề bạn muốn khai thác, tính điểm "dễ khai thác" bằng dữ
            liệu YouTube thật (tỉ lệ view/lượt sub kênh) để ưu tiên chủ đề nào
            nên tìm nguồn Trung Quốc để dịch trước.
          </p>
        </div>

        {youtubeStatus.data && !youtubeStatus.data.configured && (
          <Alert className='mb-4'>
            <AlertTitle>Chưa cấu hình YouTube Data API</AlertTitle>
            <AlertDescription>
              Vẫn thêm được chủ đề, nhưng cần API key mới tính được điểm cơ hội.
              Tạo key tại{' '}
              <a
                href='https://console.cloud.google.com/apis/credentials'
                target='_blank'
                rel='noopener noreferrer'
                className='underline'
              >
                console.cloud.google.com
              </a>{' '}
              (bật "YouTube Data API v3"), rồi thêm ở trang{' '}
              <a href='/api-keys' className='underline'>
                API Keys
              </a>{' '}
              với provider "YouTube Data API".
            </AlertDescription>
          </Alert>
        )}

        <Card className='mb-6'>
          <CardHeader>
            <CardTitle className='text-base'>Thêm chủ đề mới</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                if (name.trim()) create.mutate()
              }}
              className='grid gap-3 sm:grid-cols-2'
            >
              <div className='space-y-1.5'>
                <Label htmlFor='topic-name'>Tên chủ đề</Label>
                <Input
                  id='topic-name'
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder='Vd: Truyện ma hoạt hình'
                />
              </div>
              <div className='space-y-1.5'>
                <Label htmlFor='topic-query'>
                  Từ khoá tìm trên YouTube (tuỳ chọn)
                </Label>
                <Input
                  id='topic-query'
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder='Để trống thì dùng tên chủ đề'
                />
              </div>
              <div className='space-y-1.5 sm:col-span-2'>
                <Label htmlFor='topic-note'>Ghi chú (tuỳ chọn)</Label>
                <Textarea
                  id='topic-note'
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={2}
                />
              </div>
              <Button
                type='submit'
                disabled={!name.trim() || create.isPending}
                className='w-fit'
              >
                {create.isPending ? (
                  <Loader2 className='size-3.5 animate-spin' />
                ) : (
                  <Plus className='size-3.5' />
                )}
                Thêm chủ đề
              </Button>
            </form>
          </CardContent>
        </Card>

        {topics.isLoading && (
          <p className='flex items-center gap-2 text-muted-foreground'>
            <Loader2 className='size-4 animate-spin' />
            Đang tải...
          </p>
        )}

        {topics.data && topics.data.length === 0 && (
          <p className='text-muted-foreground'>
            Chưa có chủ đề nào — thêm chủ đề đầu tiên ở trên.
          </p>
        )}

        <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
          {topics.data?.map((topic) => (
            <TopicCard key={topic.id} topic={topic} />
          ))}
        </div>
      </Main>
    </>
  )
}
