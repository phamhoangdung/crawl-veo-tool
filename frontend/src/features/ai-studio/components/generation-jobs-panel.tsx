import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { listGenerationJobs } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

function elapsedLabel(job: {
  created_at: string
  finished_at: string | null
}): string {
  const start = new Date(job.created_at).getTime()
  const end = job.finished_at ? new Date(job.finished_at).getTime() : Date.now()
  const seconds = Math.max(0, Math.round((end - start) / 1000))
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}p${(seconds % 60).toString().padStart(2, '0')}`
}

/**
 * Các lần sinh trong phiên chạy này của backend. Có bảng này thì rời trang giữa
 * chừng rồi quay lại vẫn thấy job chạy tới đâu — trước đây chỉ có dòng chữ "có
 * thể rời trang" mà không có chỗ nào để quay lại xem.
 */
export function GenerationJobsPanel() {
  const { data: jobs } = useQuery({
    queryKey: ['ai-studio', 'jobs'],
    queryFn: listGenerationJobs,
    // Chỉ hỏi dồn khi còn job đang chạy; xong hết rồi thì thôi.
    refetchInterval: (query) =>
      query.state.data?.some((j) => j.status === 'running') ? 2000 : false,
  })

  const rows = jobs ?? []
  if (rows.length === 0) return null

  const running = rows.filter((j) => j.status === 'running').length

  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between'>
        <div>
          <CardTitle className='text-base'>
            Lần sinh gần đây ({rows.length})
          </CardTitle>
          <CardDescription>
            Job chạy trên backend, không phải trong tab này — đóng tab rồi mở lại
            vẫn theo dõi được.
          </CardDescription>
        </div>
        {running > 0 && (
          <Badge variant='secondary' className='gap-1.5'>
            <Loader2 className='size-3 animate-spin' />
            {running} đang chạy
          </Badge>
        )}
      </CardHeader>
      <CardContent className='space-y-1.5'>
        {rows.slice(0, 10).map((job) => (
          <div
            key={job.id}
            className='flex items-center gap-2 rounded-md border p-2 text-xs'
          >
            <Badge variant='outline' className='shrink-0'>
              {job.kind === 'keyframe' ? 'Ảnh' : 'Clip'}
            </Badge>
            <div className='min-w-0 flex-1'>
              <p className='truncate'>{job.label}</p>
              {job.error && (
                <p className='text-destructive truncate'>{job.error}</p>
              )}
            </div>
            <span className='text-muted-foreground shrink-0'>
              {elapsedLabel(job)}
            </span>
            <span
              className={cn(
                'w-20 shrink-0 text-end',
                job.status === 'failed'
                  ? 'text-destructive'
                  : job.status === 'done'
                    ? 'text-green-600'
                    : 'text-muted-foreground'
              )}
            >
              {job.status === 'running'
                ? 'Đang chạy'
                : job.status === 'failed'
                  ? 'Lỗi'
                  : job.from_cache
                    ? 'Dùng lại'
                    : 'Xong'}
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
