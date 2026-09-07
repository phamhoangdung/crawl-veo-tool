import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  AudioLines,
  Captions,
  Download,
  FolderOpen,
  Languages,
  Mic,
  X,
} from 'lucide-react'
import { toast } from 'sonner'
import {
  clearFinishedTasks,
  clearTaskProgress,
  revealInFileManager,
  type TaskKind,
  type TaskProgress,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  useTaskProgress,
  useTaskProgressStream,
} from '@/hooks/use-task-progress'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'

const KIND_ICONS: Record<TaskKind, typeof Download> = {
  download: Download,
  transcribe: Captions,
  translate: Languages,
  dub: Mic,
  burn: AudioLines,
}

function formatBytes(bytes: number) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

/** Dòng mô tả tiến độ — tải đếm theo byte, các bước khác đếm theo số câu. */
function describeProgress(task: TaskProgress) {
  if (task.stage === 'failed') return task.error ?? 'Thất bại'
  if (task.stage === 'done') return 'Hoàn tất'

  if (task.kind === 'download') {
    const size = task.total
      ? `${task.percent}% (${formatBytes(task.current)} / ${formatBytes(task.total)})`
      : formatBytes(task.current)
    const speed = task.speed_per_sec > 0 ? ` · ${formatBytes(task.speed_per_sec)}/s` : ''
    return `${task.stage_label} · ${size}${speed}`
  }

  if (task.total) {
    return `${task.stage_label} · ${task.current}/${task.total} câu (${task.percent}%)`
  }
  return task.stage_label
}

function TaskRow({ task }: { task: TaskProgress }) {
  const queryClient = useQueryClient()
  const Icon = KIND_ICONS[task.kind] ?? Activity

  const isDone = task.stage === 'done'
  const isFailed = task.stage === 'failed'

  const reveal = useMutation({
    mutationFn: () => revealInFileManager(task.video_id),
    onError: () => toast.error('Không mở được thư mục.'),
  })

  const dismiss = useMutation({
    mutationFn: () => clearTaskProgress(task.video_id, task.kind),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      queryClient.invalidateQueries({ queryKey: ['files'] })
    },
  })

  return (
    <div className='space-y-1.5 px-3 py-2'>
      <div className='flex items-start gap-2'>
        <Icon
          className={cn(
            'mt-0.5 size-3.5 shrink-0',
            isFailed ? 'text-destructive' : isDone ? 'text-green-600' : 'text-primary'
          )}
        />
        <div className='min-w-0 flex-1'>
          <p className='line-clamp-1 text-xs font-medium'>{task.title}</p>
          <p className='text-[11px] text-muted-foreground'>{task.kind_label}</p>
        </div>
        {isDone && (
          <Button
            size='icon'
            variant='ghost'
            className='size-5 shrink-0'
            title='Mở vị trí file'
            onClick={() => reveal.mutate()}
          >
            <FolderOpen className='size-3' />
          </Button>
        )}
        {!task.is_running && (
          <Button
            size='icon'
            variant='ghost'
            className='size-5 shrink-0'
            title='Bỏ khỏi danh sách'
            onClick={() => dismiss.mutate()}
          >
            <X className='size-3' />
          </Button>
        )}
      </div>

      <div className='h-1 overflow-hidden rounded-full bg-muted'>
        <div
          className={cn(
            'h-full rounded-full',
            isFailed
              ? 'bg-destructive'
              : isDone
                ? 'bg-green-500'
                : 'bg-primary transition-[width] duration-300',
            // Chặng không đo được (transcribe, demucs) — chạy sọc động thay vì
            // thanh đứng im ở 0%.
            task.is_running && !task.total && 'animate-pulse'
          )}
          style={{
            width: isDone || isFailed ? '100%' : task.total ? `${task.percent}%` : '100%',
          }}
        />
      </div>

      <p
        className={cn(
          'text-[11px]',
          isFailed ? 'text-destructive' : 'text-muted-foreground'
        )}
      >
        {describeProgress(task)}
      </p>
    </div>
  )
}

/**
 * Icon trên topbar theo dõi mọi tác vụ đang chạy (tải, tách lời thoại, dịch,
 * lồng tiếng). Tác vụ chạy nền nên người dùng phải thấy được từ bất kỳ trang nào.
 */
export function TaskMonitor() {
  const queryClient = useQueryClient()

  // Nơi duy nhất mở SSE — component này có mặt trên mọi trang.
  useTaskProgressStream()
  const tasks = useTaskProgress()

  const clearFinished = useMutation({
    mutationFn: clearFinishedTasks,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      queryClient.invalidateQueries({ queryKey: ['files'] })
    },
  })

  const items = tasks
  const running = items.filter((t) => t.is_running)
  const failed = items.filter((t) => t.stage === 'failed')
  const finished = items.filter((t) => !t.is_running)

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant='ghost'
          size='icon'
          className='relative'
          title='Tác vụ đang chạy'
        >
          <Activity className={cn('size-5', running.length > 0 && 'text-primary')} />
          {running.length > 0 && (
            <span className='absolute -end-0.5 -top-0.5 flex size-4 items-center justify-center rounded-full bg-primary text-[10px] font-medium text-primary-foreground'>
              {running.length}
            </span>
          )}
          {running.length === 0 && failed.length > 0 && (
            <span className='absolute -end-0.5 -top-0.5 flex size-4 items-center justify-center rounded-full bg-destructive text-[10px] font-medium text-destructive-foreground'>
              {failed.length}
            </span>
          )}
        </Button>
      </PopoverTrigger>

      <PopoverContent align='end' className='w-88 p-0'>
        <div className='flex items-center gap-2 border-b px-3 py-2'>
          <p className='flex-1 text-sm font-medium'>
            {running.length > 0 ? `Đang chạy ${running.length}` : 'Tác vụ'}
          </p>
          {failed.length > 0 && (
            <Badge variant='destructive' className='h-5'>
              {failed.length} lỗi
            </Badge>
          )}
          {finished.length > 0 && (
            <Button
              size='sm'
              variant='ghost'
              className='h-6 px-2 text-xs'
              disabled={clearFinished.isPending}
              onClick={() => clearFinished.mutate()}
            >
              Dọn xong
            </Button>
          )}
        </div>

        {items.length === 0 ? (
          <p className='px-3 py-6 text-center text-xs text-muted-foreground'>
            Chưa có tác vụ nào đang chạy.
          </p>
        ) : (
          <ScrollArea className='max-h-80'>
            <div className='divide-y'>
              {items.map((task) => (
                <TaskRow key={`${task.video_id}-${task.kind}`} task={task} />
              ))}
            </div>
          </ScrollArea>
        )}
      </PopoverContent>
    </Popover>
  )
}
