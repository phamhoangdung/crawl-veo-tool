import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Play, Square } from 'lucide-react'
import { toast } from 'sonner'
import {
  cancelBatch,
  getApiErrorMessage,
  getBatchStatus,
  getPendingVideoIds,
  startBatch,
  type BatchStep,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'

const STEP_LABELS: { value: BatchStep; label: string }[] = [
  { value: 'download', label: 'Tải video' },
  { value: 'transcribe', label: 'Tách lời thoại' },
  { value: 'translate', label: 'Dịch phụ đề' },
  { value: 'dub', label: 'Lồng tiếng' },
  { value: 'burn', label: 'Ghép phụ đề cứng' },
]

// Khớp với DEFAULT_STEPS của backend: "burn" là lựa chọn phong cách, không phải
// bước ai cũng cần, nên không bật sẵn.
const DEFAULT_STEPS: BatchStep[] = [
  'download',
  'transcribe',
  'translate',
  'dub',
]

const ITEM_STATUS_LABELS: Record<string, string> = {
  pending: 'Chờ',
  running: 'Đang chạy',
  done: 'Xong',
  failed: 'Lỗi',
  skipped: 'Bỏ qua',
}

export function BatchPanel() {
  const queryClient = useQueryClient()
  const [steps, setSteps] = useState<BatchStep[]>(DEFAULT_STEPS)
  const [concurrency, setConcurrency] = useState(1)

  // Chỉ hỏi lại liên tục khi có batch đang chạy — batch xong rồi mà vẫn poll 2
  // giây/lần thì chỉ tổ làm ồn log backend.
  const { data: status } = useQuery({
    queryKey: ['batch-status'],
    queryFn: getBatchStatus,
    refetchInterval: (query) =>
      query.state.data?.is_running ? 2000 : false,
  })

  const { data: pendingIds } = useQuery({
    queryKey: ['batch-pending'],
    queryFn: () => getPendingVideoIds(50),
  })

  const isRunning = status?.is_running ?? false
  const pendingCount = pendingIds?.length ?? 0

  const start = useMutation({
    mutationFn: () => {
      if (!pendingIds || pendingIds.length === 0) {
        throw new Error('Không có video nào cần chạy')
      }
      return startBatch(pendingIds, steps, concurrency)
    },
    onSuccess: (job) => {
      queryClient.setQueryData(['batch-status'], job)
      toast.success(`Đã bắt đầu chạy ${job.total} video.`)
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, 'Không bắt đầu được batch.'))
    },
  })

  const cancel = useMutation({
    mutationFn: cancelBatch,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['batch-status'] })
      toast.success('Đã yêu cầu dừng — video đang chạy dở sẽ chạy nốt bước hiện tại.')
    },
    onError: () => toast.error('Không dừng được batch.'),
  })

  function toggleStep(step: BatchStep, checked: boolean) {
    setSteps((prev) =>
      checked
        ? // Giữ đúng thứ tự pipeline chứ không theo thứ tự bấm: backend chạy
          // tuần tự theo danh sách nhận được, đảo thứ tự là hỏng.
          STEP_LABELS.filter((s) => s.value === step || prev.includes(s.value)).map(
            (s) => s.value
          )
        : prev.filter((s) => s !== step)
    )
  }

  const progressPercent =
    status && status.total > 0
      ? ((status.done + status.failed + status.skipped) / status.total) * 100
      : 0

  return (
    <Card className='mb-6'>
      <CardHeader>
        <CardTitle className='text-base'>Chạy hàng loạt</CardTitle>
        <CardDescription>
          Chạy cả pipeline cho mọi video chưa xong, không phải bấm từng nút cho
          từng video.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-4'>
        <div className='flex flex-wrap gap-4'>
          {STEP_LABELS.map((step) => (
            <div key={step.value} className='flex items-center gap-2'>
              <Checkbox
                id={`batch-${step.value}`}
                checked={steps.includes(step.value)}
                disabled={isRunning}
                onCheckedChange={(checked) =>
                  toggleStep(step.value, checked === true)
                }
              />
              <Label
                htmlFor={`batch-${step.value}`}
                className='text-xs font-normal'
              >
                {step.label}
              </Label>
            </div>
          ))}
        </div>

        <div className='flex flex-wrap items-end gap-3'>
          <div className='space-y-1'>
            <Label htmlFor='batch-concurrency' className='text-xs font-normal'>
              Số video chạy cùng lúc
            </Label>
            <select
              id='batch-concurrency'
              className='h-8 rounded-md border bg-transparent px-2 text-xs'
              value={concurrency}
              disabled={isRunning}
              onChange={(e) => setConcurrency(Number(e.target.value))}
            >
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>

          {isRunning ? (
            <Button
              variant='destructive'
              size='sm'
              className='gap-1.5'
              disabled={cancel.isPending}
              onClick={() => cancel.mutate()}
            >
              <Square className='size-3.5' />
              Dừng
            </Button>
          ) : (
            <Button
              size='sm'
              className='gap-1.5'
              disabled={
                start.isPending || pendingCount === 0 || steps.length === 0
              }
              onClick={() => start.mutate()}
            >
              {start.isPending ? (
                <Loader2 className='size-3.5 animate-spin' />
              ) : (
                <Play className='size-3.5' />
              )}
              {pendingCount === 0
                ? 'Không có video nào cần chạy'
                : `Chạy ${pendingCount} video chưa xong`}
            </Button>
          )}
        </div>

        <p className='text-[11px] text-muted-foreground'>
          Để 1 video cùng lúc là hợp lý nhất: tách lời thoại và tách nhạc nền đã
          ăn hết CPU, chạy 2 video song song chỉ làm cả hai cùng chậm.
        </p>

        {status && (
          <div className='space-y-2 border-t pt-3'>
            <div className='flex items-center justify-between text-xs'>
              <span className='font-medium'>
                {isRunning
                  ? 'Đang chạy'
                  : status.cancelled
                    ? 'Đã dừng'
                    : 'Lần chạy gần nhất'}
              </span>
              <span className='text-muted-foreground'>
                {status.done} xong · {status.failed} lỗi · {status.skipped} bỏ
                qua · {status.pending} chờ
              </span>
            </div>

            <div className='h-1 overflow-hidden rounded-full bg-muted'>
              <div
                className={cn(
                  'h-full rounded-full transition-[width] duration-300',
                  status.failed > 0 ? 'bg-amber-500' : 'bg-primary'
                )}
                style={{ width: `${progressPercent}%` }}
              />
            </div>

            <div className='max-h-48 space-y-1 overflow-y-auto'>
              {status.items.map((item) => (
                <div
                  key={item.video_id}
                  className='flex items-center gap-2 text-[11px]'
                >
                  <span
                    className={cn(
                      'w-16 shrink-0',
                      item.status === 'failed'
                        ? 'text-destructive'
                        : item.status === 'done'
                          ? 'text-green-600'
                          : 'text-muted-foreground'
                    )}
                  >
                    {ITEM_STATUS_LABELS[item.status] ?? item.status}
                  </span>
                  <span className='min-w-0 flex-1 truncate'>{item.title}</span>
                  <span className='shrink-0 text-muted-foreground'>
                    {item.error ?? item.current_step ?? ''}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
