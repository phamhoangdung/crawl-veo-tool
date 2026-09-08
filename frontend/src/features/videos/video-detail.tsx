import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from '@tanstack/react-router'
import {
  ArrowLeft,
  Captions,
  Download,
  ExternalLink,
  FolderOpen,
  Languages,
  Mic,
  Pencil,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'
import {
  burnSubtitles,
  deleteFileVariant,
  downloadVideo,
  dubVideo,
  getDownloadUrl,
  getVideoDetail,
  getVideoFilesById,
  revealInFileManager,
  transcribeVideo,
  translateVideo,
  type TaskKind,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { useTaskProgress } from '@/hooks/use-task-progress'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfigDrawer } from '@/components/config-drawer'
import { CoverImage } from '@/components/cover-image'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { TaskMonitor } from '@/components/task-monitor'
import { ThemeSwitch } from '@/components/theme-switch'
import { TimelineEditor } from '@/features/editor'
import { SubtitleEditor } from './subtitle-editor'

function formatBytes(bytes: number) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

function formatDuration(seconds: number | null) {
  if (seconds === null) return '—'
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes}:${rest.toString().padStart(2, '0')}`
}

const VARIANT_LABELS: Record<string, string> = {
  original: 'Gốc',
  dubbed: 'Lồng tiếng',
  burned: 'Có phụ đề',
}

/**
 * Các bước xử lý. `requires` là điều kiện tiên quyết — hiển thị lý do khoá nút
 * thay vì để người dùng bấm rồi nhận lỗi 400 từ backend.
 */
type StepContext = {
  hasFile: boolean
  hasTranscript: boolean
  hasTranslation: boolean
}

type StepDef = {
  kind: TaskKind
  label: string
  icon: typeof Captions
  description: string
  run: (id: number) => Promise<unknown>
  requires: (ctx: StepContext) => string | null
}

const STEPS: StepDef[] = [
  {
    kind: 'download',
    label: 'Tải video',
    icon: Download,
    description: 'Tải video gốc từ Bilibili về máy.',
    run: downloadVideo,
    requires: ({ hasFile }) => (hasFile ? 'Đã có file gốc' : null),
  },
  {
    kind: 'transcribe',
    label: 'Tách lời thoại',
    icon: Captions,
    description: 'Nhận dạng lời thoại tiếng Trung bằng faster-whisper.',
    run: transcribeVideo,
    requires: ({ hasFile }) => (hasFile ? null : 'Cần tải video trước'),
  },
  {
    kind: 'translate',
    label: 'Dịch phụ đề',
    icon: Languages,
    description: 'Dịch lời thoại sang tiếng Việt.',
    run: (id) => translateVideo(id),
    requires: ({ hasTranscript }) =>
      hasTranscript ? null : 'Cần tách lời thoại trước',
  },
  {
    kind: 'dub',
    label: 'Lồng tiếng',
    icon: Mic,
    description: 'Tạo giọng đọc tiếng Việt, giữ lại nhạc nền gốc.',
    run: (id) => dubVideo(id),
    requires: ({ hasTranslation }) => (hasTranslation ? null : 'Cần dịch phụ đề trước'),
  },
  {
    kind: 'burn',
    label: 'Ghép phụ đề vào video',
    icon: Captions,
    description: 'Chèn cứng phụ đề song ngữ vào khung hình.',
    run: burnSubtitles,
    requires: ({ hasTranslation }) => (hasTranslation ? null : 'Cần dịch phụ đề trước'),
  },
]

function StepCard({
  step,
  videoId,
  blockedReason,
}: {
  step: StepDef
  videoId: number
  blockedReason: string | null
}) {
  const queryClient = useQueryClient()

  // Tiến độ của đúng tác vụ này, đọc từ cache do SSE cập nhật.
  const tasks = useTaskProgress()
  const task = tasks.find((t) => t.video_id === videoId && t.kind === step.kind)
  const isRunning = task?.is_running ?? false

  const run = useMutation({
    mutationFn: () => step.run(videoId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      queryClient.invalidateQueries({ queryKey: ['files'] })
      queryClient.invalidateQueries({ queryKey: ['video', videoId] })
      toast.success(`Đã bắt đầu: ${step.label}`)
    },
    onError: (error) => {
      const detail =
        error && typeof error === 'object' && 'response' in error
          ? ((error as { response?: { data?: { detail?: string } } }).response?.data
              ?.detail ?? null)
          : null
      toast.error(detail ?? `Không chạy được: ${step.label}`)
    },
  })

  const Icon = step.icon
  const isDone = task?.stage === 'done'
  const isFailed = task?.stage === 'failed'

  return (
    <div className='space-y-2 rounded-lg border p-4'>
      <div className='flex items-start gap-3'>
        <Icon className='mt-0.5 size-4 shrink-0 text-muted-foreground' />
        <div className='min-w-0 flex-1'>
          <p className='text-sm font-medium'>{step.label}</p>
          <p className='text-xs text-muted-foreground'>{step.description}</p>
        </div>
        <Button
          size='sm'
          variant={isDone ? 'outline' : 'default'}
          disabled={isRunning || run.isPending || blockedReason !== null}
          onClick={() => run.mutate()}
        >
          {isRunning ? 'Đang chạy...' : isDone ? 'Chạy lại' : 'Chạy'}
        </Button>
      </div>

      {blockedReason && (
        <p className='ps-7 text-xs text-muted-foreground'>{blockedReason}</p>
      )}

      {task && (
        <div className='space-y-1 ps-7'>
          <div className='h-1 overflow-hidden rounded-full bg-muted'>
            <div
              className={cn(
                'h-full rounded-full',
                isFailed
                  ? 'bg-destructive'
                  : isDone
                    ? 'bg-green-500'
                    : 'bg-primary transition-[width] duration-300',
                // Chặng không đo được (whisper, demucs) — sọc động thay vì đứng im.
                isRunning && !task.total && 'animate-pulse'
              )}
              style={{
                width:
                  isDone || isFailed ? '100%' : task.total ? `${task.percent}%` : '100%',
              }}
            />
          </div>
          <p
            className={cn(
              'text-[11px]',
              isFailed ? 'text-destructive' : 'text-muted-foreground'
            )}
          >
            {isFailed
              ? (task.error ?? 'Thất bại')
              : isDone
                ? 'Hoàn tất'
                : task.total
                  ? `${task.stage_label} · ${task.current}/${task.total} (${task.percent}%)`
                  : task.stage_label}
          </p>
        </div>
      )}
    </div>
  )
}

export function VideoDetail() {
  // Lấy id từ URL thay vì props: route file chỉ nên export Route để fast-refresh
  // hoạt động.
  const { videoId: rawVideoId } = useParams({
    from: '/_authenticated/videos/$videoId',
  })
  const videoId = Number(rawVideoId)

  const queryClient = useQueryClient()
  const [editorOpen, setEditorOpen] = useState(false)

  const { data: files, isLoading: filesLoading } = useQuery({
    queryKey: ['files', videoId],
    queryFn: () => getVideoFilesById(videoId),
  })

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['video', videoId],
    queryFn: () => getVideoDetail(videoId),
  })

  const reveal = useMutation({
    mutationFn: () => revealInFileManager(videoId),
    onError: () => toast.error('Không mở được thư mục.'),
  })

  const removeVariant = useMutation({
    mutationFn: (variant: string) => deleteFileVariant(videoId, variant),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['files'] })
      queryClient.invalidateQueries({ queryKey: ['video', videoId] })
      toast.success('Đã xoá file.')
    },
    onError: () => toast.error('Không xoá được file.'),
  })

  const isLoading = filesLoading || detailLoading
  const transcript = detail?.transcript ?? []
  const fileList = files?.files ?? []
  const hasFile = fileList.some((f) => f.variant === 'original' && f.exists)
  const hasTranscript = transcript.length > 0
  const hasTranslation = transcript.some((s) => s.translated_text?.trim())

  const title = files?.title ?? detail?.title ?? 'Video'

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
        <Button asChild variant='ghost' size='sm' className='mb-3 -ms-2 gap-1'>
          <Link to='/videos'>
            <ArrowLeft className='size-4' />
            Video của tôi
          </Link>
        </Button>

        {isLoading ? (
          <div className='space-y-4'>
            <Skeleton className='h-8 w-2/3' />
            <div className='grid gap-6 lg:grid-cols-3'>
              <Skeleton className='h-64 lg:col-span-1' />
              <Skeleton className='h-64 lg:col-span-2' />
            </div>
          </div>
        ) : (
          <>
            <div className='mb-6'>
              <h1 className='text-2xl font-bold tracking-tight'>{title}</h1>
              <div className='mt-2 flex flex-wrap items-center gap-3 text-sm text-muted-foreground'>
                <Badge variant='outline'>{detail?.status ?? files?.status}</Badge>
                {detail?.author_name && <span>{detail.author_name}</span>}
                <span>{formatDuration(detail?.duration_seconds ?? null)}</span>
                <span>{formatBytes(files?.total_bytes ?? 0)}</span>
                {detail?.source_url && (
                  <a
                    href={detail.source_url}
                    target='_blank'
                    rel='noreferrer'
                    className='inline-flex items-center gap-1 hover:underline'
                  >
                    Xem trên Bilibili
                    <ExternalLink className='size-3' />
                  </a>
                )}
              </div>
            </div>

            {detail?.error_message && (
              <p className='mb-6 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive'>
                {detail.error_message}
              </p>
            )}

            <div className='grid gap-6 lg:grid-cols-3'>
              {/* Cột trái: ảnh + file. Cột phải rộng hơn cho luồng xử lý. */}
              <div className='space-y-6 lg:col-span-1'>
                <CoverImage
                  src={files?.cover_url ?? detail?.cover_url ?? null}
                  className='w-full rounded-lg'
                />

                <Card>
                  <CardHeader>
                    <div className='flex items-center justify-between'>
                      <CardTitle className='text-base'>
                        File ({fileList.length})
                      </CardTitle>
                      <Button
                        size='sm'
                        variant='ghost'
                        className='h-7 gap-1 text-xs'
                        onClick={() => reveal.mutate()}
                      >
                        <FolderOpen className='size-3' />
                        Mở thư mục
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {fileList.length === 0 ? (
                      <p className='text-sm text-muted-foreground'>
                        Chưa có file nào.
                      </p>
                    ) : (
                      <ul className='space-y-1.5'>
                        {fileList.map((file) => (
                          <li
                            key={file.variant}
                            className='flex items-center gap-2 rounded border px-2 py-1.5 text-xs'
                          >
                            <Badge variant='outline' className='shrink-0'>
                              {VARIANT_LABELS[file.variant] ?? file.variant}
                            </Badge>
                            <span className='flex-1 text-muted-foreground'>
                              {file.exists
                                ? formatBytes(file.size_bytes)
                                : 'Không còn trên đĩa'}
                            </span>
                            {file.exists && (
                              <>
                                <a
                                  href={getDownloadUrl(videoId, file.variant)}
                                  title='Tải về máy'
                                  className='text-muted-foreground hover:text-foreground'
                                >
                                  <Download className='size-3.5' />
                                </a>
                                <button
                                  type='button'
                                  title='Xoá file này'
                                  className='text-muted-foreground hover:text-destructive'
                                  disabled={removeVariant.isPending}
                                  onClick={() => removeVariant.mutate(file.variant)}
                                >
                                  <Trash2 className='size-3.5' />
                                </button>
                              </>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </CardContent>
                </Card>
              </div>

              <div className='space-y-6 lg:col-span-2'>
                <Card>
                  <CardHeader>
                    <CardTitle className='text-base'>Các bước xử lý</CardTitle>
                    <CardDescription>
                      Pipeline chạy tuần tự — mỗi bước cần kết quả của bước trước.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className='space-y-3'>
                    {STEPS.map((step) => (
                      <StepCard
                        key={step.kind}
                        step={step}
                        videoId={videoId}
                        blockedReason={step.requires({
                          hasFile,
                          hasTranscript,
                          hasTranslation,
                        })}
                      />
                    ))}
                  </CardContent>
                </Card>

                {hasTranscript && (
                  <Card>
                    <CardHeader>
                      <div className='flex items-center justify-between'>
                        <div>
                          <CardTitle className='text-base'>
                            Phụ đề ({transcript.length} câu)
                          </CardTitle>
                          <CardDescription>
                            {hasTranslation
                              ? 'Nên xem lại và sửa trước khi lồng tiếng — giọng đọc theo đúng bản dịch này.'
                              : 'Chưa dịch sang tiếng Việt.'}
                          </CardDescription>
                        </div>
                        <Button
                          size='sm'
                          variant='outline'
                          className='gap-1'
                          onClick={() => setEditorOpen(true)}
                        >
                          <Pencil className='size-3.5' />
                          Xem trước & sửa
                        </Button>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <ul className='space-y-2'>
                        {transcript.slice(0, 5).map((segment, index) => (
                          <li key={index} className='rounded border px-3 py-2 text-sm'>
                            <p className='text-xs text-muted-foreground tabular-nums'>
                              {formatDuration(Math.floor(segment.start))}
                            </p>
                            <p>{segment.text}</p>
                            {segment.translated_text && (
                              <p className='text-primary'>{segment.translated_text}</p>
                            )}
                          </li>
                        ))}
                      </ul>
                      {transcript.length > 5 && (
                        <>
                          <Separator className='my-3' />
                          <button
                            type='button'
                            onClick={() => setEditorOpen(true)}
                            className='text-sm text-muted-foreground hover:underline'
                          >
                            Xem tất cả {transcript.length} câu →
                          </button>
                        </>
                      )}
                    </CardContent>
                  </Card>
                )}

              </div>
            </div>

            <SubtitleEditor
              videoId={videoId}
              title={title}
              segments={transcript}
              availableVariants={{
                burned: fileList.some((f) => f.variant === 'burned' && f.exists),
                dubbed: fileList.some((f) => f.variant === 'dubbed' && f.exists),
                original: hasFile,
              }}
              open={editorOpen}
              onOpenChange={setEditorOpen}
            />

            {/* Editor cần nhiều chiều ngang nên đặt full-width dưới 2 cột,
                không nhét vào cột phải và không bọc trong popup. */}
            {hasFile && (
              <section className='mt-6'>
                <div className='mb-3'>
                  <h2 className='text-lg font-semibold'>Trình chỉnh sửa timeline</h2>
                  <p className='text-sm text-muted-foreground'>
                    Cắt/sắp xếp lại video, thêm overlay/CTA, chuyển cảnh, chỉnh âm lượng —
                    AI chỉ gợi ý, bạn kéo-chỉnh rồi bấm Render.
                  </p>
                </div>
                <TimelineEditor videoId={videoId} />
              </section>
            )}
          </>
        )}
      </Main>
    </>
  )
}
