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
  Trash2,
  Users,
} from 'lucide-react'
import { toast } from 'sonner'
import {
  burnSubtitles,
  deleteFileVariant,
  diarizeVideo,
  downloadVideo,
  dubVideo,
  getApiErrorMessage,
  getAppSettings,
  getDownloadUrl,
  getVideoDetail,
  getVideoFilesById,
  revealInFileManager,
  transcribeVideo,
  translateVideo,
  type TaskKind,
} from '@/lib/api'
import { formatBytes, formatDuration } from '@/lib/format'
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
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import { CoverImage } from '@/components/cover-image'
import { AppHeader } from '@/components/layout/app-header'
import { Main } from '@/components/layout/main'
import { TimelineEditor } from '@/features/editor'
import { SpeakerVoices } from './speaker-voices'
import { SubtitleEditor } from './subtitle-editor'
import { SubtitleReview } from './subtitle-review'

const VARIANT_LABELS: Record<string, string> = {
  original: 'Gốc',
  dubbed: 'Lồng tiếng',
  burned: 'Có phụ đề',
}

/**
 * Processing steps. `requires` is a prerequisite — shows the reason a button is locked
 * instead of letting the user click and get a 400 error from the backend.
 */
type StepContext = {
  hasFile: boolean
  hasTranscript: boolean
  hasTranslation: boolean
}

/** Options of a step, shown right on the run button. Previously only changeable by
 * editing query params — meaning real users could not change them. */
type StepOption =
  | {
      key: string
      type: 'switch'
      label: string
      hint?: string
      default: boolean
    }
  | {
      key: string
      type: 'select'
      label: string
      hint?: string
      default: string
      choices: { value: string; label: string }[]
    }
  | {
      key: string
      type: 'color'
      label: string
      hint?: string
      default: string
    }

type StepOptionValues = Record<string, boolean | string>

type StepDef = {
  kind: TaskKind
  label: string
  icon: typeof Captions
  description: string
  run: (id: number, options: StepOptionValues) => Promise<unknown>
  requires: (ctx: StepContext) => string | null
  options?: StepOption[]
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
    kind: 'diarize',
    label: 'Phân vai người nói',
    icon: Users,
    description:
      'Tự nhận diện có bao nhiêu người nói khác nhau trong video, tách theo từng vai để gán giọng đọc riêng (không bắt buộc).',
    run: (id) => diarizeVideo(id),
    requires: ({ hasTranscript }) => (hasTranscript ? null : 'Cần tách lời thoại trước'),
  },
  {
    kind: 'dub',
    label: 'Lồng tiếng',
    icon: Mic,
    description: 'Tạo giọng đọc tiếng Việt, giữ lại nhạc nền gốc.',
    run: (id, options) => dubVideo(id, options.keepBackground as boolean),
    requires: ({ hasTranslation }) => (hasTranslation ? null : 'Cần dịch phụ đề trước'),
    options: [
      {
        key: 'keepBackground',
        type: 'switch',
        label: 'Giữ nhạc nền gốc',
        hint: 'Tách nhạc nền bằng Demucs rồi trộn lại với giọng đọc. Tắt đi thì nhanh hơn hẳn nhưng video sẽ mất sạch âm thanh gốc (nhạc, tiếng động).',
        default: true,
      },
    ],
  },
  {
    kind: 'burn',
    label: 'Ghép phụ đề vào video',
    icon: Captions,
    description: 'Chèn cứng phụ đề song ngữ vào khung hình.',
    run: (id, options) =>
      burnSubtitles(id, {
        position: options.position as 'bottom' | 'top',
        font_family: options.fontFamily as string,
        font_color: (options.fontColor as string).replace('#', ''),
        bold: options.bold as boolean,
      }),
    requires: ({ hasTranslation }) => (hasTranslation ? null : 'Cần dịch phụ đề trước'),
    options: [
      {
        key: 'position',
        type: 'select',
        label: 'Vị trí phụ đề',
        hint: 'Chọn "Trên" khi video gốc đã có phụ đề cháy sẵn ở dưới — để mặc định thì hai lớp chữ chồng lên nhau, không đọc được lớp nào.',
        default: 'bottom',
        choices: [
          { value: 'bottom', label: 'Dưới (mặc định)' },
          { value: 'top', label: 'Trên' },
        ],
      },
      {
        key: 'fontFamily',
        type: 'select',
        label: 'Font chữ',
        default: 'be-vietnam-pro',
        // Matches the ids in the backend `font_service.py` — all 4 have the official
        // "vietnamese" subset on Google Fonts (diacritic glyphs checked).
        choices: [
          { value: 'be-vietnam-pro', label: 'Be Vietnam Pro' },
          { value: 'barlow', label: 'Barlow' },
          { value: 'fira-sans', label: 'Fira Sans' },
          { value: 'anton', label: 'Anton (đậm sẵn, kiểu caption)' },
        ],
      },
      {
        key: 'fontColor',
        type: 'color',
        label: 'Màu chữ',
        default: '#FFFFFF',
      },
      {
        key: 'bold',
        type: 'switch',
        label: 'Chữ đậm',
        default: false,
      },
    ],
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

  // Progress of exactly this task, read from the cache updated by SSE.
  const tasks = useTaskProgress()
  const task = tasks.find((t) => t.video_id === videoId && t.kind === step.kind)
  const isRunning = task?.is_running ?? false

  // Initialize from each option's `default` right in `useState` rather than syncing
  // with an effect — STEPS is a constant, there is nothing to sync again.
  const [optionValues, setOptionValues] = useState<StepOptionValues>(() =>
    Object.fromEntries((step.options ?? []).map((o) => [o.key, o.default]))
  )

  const run = useMutation({
    mutationFn: () => step.run(videoId, optionValues),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      queryClient.invalidateQueries({ queryKey: ['files'] })
      queryClient.invalidateQueries({ queryKey: ['video', videoId] })
      toast.success(`Đã bắt đầu: ${step.label}`)
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, `Không chạy được: ${step.label}`))
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

      {step.options && step.options.length > 0 && (
        <div className='space-y-2 ps-7'>
          {step.options.map((option) => (
            <div key={option.key} className='space-y-1'>
              <div className='flex items-center gap-2'>
                {option.type === 'switch' ? (
                  <>
                    <Switch
                      id={`${step.kind}-${option.key}`}
                      checked={optionValues[option.key] as boolean}
                      disabled={isRunning || run.isPending}
                      onCheckedChange={(checked) =>
                        setOptionValues((prev) => ({
                          ...prev,
                          [option.key]: checked,
                        }))
                      }
                    />
                    <Label
                      htmlFor={`${step.kind}-${option.key}`}
                      className='text-xs font-normal'
                    >
                      {option.label}
                    </Label>
                  </>
                ) : option.type === 'color' ? (
                  <>
                    <Label
                      htmlFor={`${step.kind}-${option.key}`}
                      className='text-xs font-normal'
                    >
                      {option.label}
                    </Label>
                    <input
                      id={`${step.kind}-${option.key}`}
                      type='color'
                      className='h-7 w-10 cursor-pointer rounded-md border bg-transparent p-0.5'
                      value={optionValues[option.key] as string}
                      disabled={isRunning || run.isPending}
                      onChange={(e) =>
                        setOptionValues((prev) => ({
                          ...prev,
                          [option.key]: e.target.value,
                        }))
                      }
                    />
                  </>
                ) : (
                  <>
                    <Label
                      htmlFor={`${step.kind}-${option.key}`}
                      className='text-xs font-normal'
                    >
                      {option.label}
                    </Label>
                    <select
                      id={`${step.kind}-${option.key}`}
                      className='h-7 rounded-md border bg-transparent px-2 text-xs'
                      value={optionValues[option.key] as string}
                      disabled={isRunning || run.isPending}
                      onChange={(e) =>
                        setOptionValues((prev) => ({
                          ...prev,
                          [option.key]: e.target.value,
                        }))
                      }
                    >
                      {option.choices.map((choice) => (
                        <option key={choice.value} value={choice.value}>
                          {choice.label}
                        </option>
                      ))}
                    </select>
                  </>
                )}
              </div>
              {option.hint && (
                <p className='text-[11px] text-muted-foreground'>{option.hint}</p>
              )}
            </div>
          ))}
        </div>
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
                // A stage that cannot be measured (whisper, demucs) — animated stripes instead of standing still.
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
  // Take the id from the URL instead of props: a route file should only export Route so fast-refresh
  // works.
  const { videoId: rawVideoId } = useParams({
    from: '/_authenticated/videos/$videoId',
  })
  const videoId = Number(rawVideoId)

  const queryClient = useQueryClient()
  const [editorOpen, setEditorOpen] = useState(false)
  // Track the open tab to hide the cover image/title/badge block when on the "Dựng
  // video" tab — the preview frame in there already shows the video, and this block only takes
  // extra vertical space unnecessarily while editing.
  const [activeTab, setActiveTab] = useState('pipeline')

  const { data: files, isLoading: filesLoading } = useQuery({
    queryKey: ['files', videoId],
    queryFn: () => getVideoFilesById(videoId),
  })

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['video', videoId],
    queryFn: () => getVideoDetail(videoId),
  })

  // Speaker separation is optional (Settings > Dubbing, off by default) — when off,
  // hide the "Speakers" step and the "Voices" tab to keep things tidy.
  const { data: appSettings } = useQuery({
    queryKey: ['app-settings'],
    queryFn: getAppSettings,
  })
  const diarizationOn = appSettings?.speaker_diarization_enabled ?? false
  const steps = STEPS.filter((s) => s.kind !== 'diarize' || diarizationOn)

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
  const hasSpeakers = transcript.some((s) => s.speaker?.trim())

  const title = files?.title ?? detail?.title ?? 'Video'

  return (
    <>
      <AppHeader />

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
            {activeTab === 'editor' ? (
              <h1 className='mb-6 truncate text-xl font-semibold tracking-tight'>
                {title}
              </h1>
            ) : (
              <div className='mb-6 flex gap-4'>
                <CoverImage
                  src={files?.cover_url ?? detail?.cover_url ?? null}
                  className='hidden w-40 shrink-0 rounded-lg sm:block'
                />
                <div className='min-w-0'>
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
              </div>
            )}

            {detail?.error_message && (
              <p className='mb-6 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive'>
                {detail.error_message}
              </p>
            )}

            {/* 3 tabs for 3 different jobs: run the pipeline, review subtitles, build
                the video. Dumping everything on 1 page makes 7 cards side by side, with
                no way to see which job is currently needed. */}
            <Tabs value={activeTab} onValueChange={setActiveTab} className='space-y-6'>
              <TabsList>
                <TabsTrigger value='pipeline'>Xử lý</TabsTrigger>
                <TabsTrigger value='subtitles' disabled={!hasTranscript}>
                  Phụ đề
                  {hasTranscript && (
                    <span className='ms-1.5 text-xs text-muted-foreground'>
                      {transcript.length}
                    </span>
                  )}
                </TabsTrigger>
                {diarizationOn && (
                  <TabsTrigger value='voices' disabled={!hasSpeakers}>
                    Giọng đọc
                  </TabsTrigger>
                )}
                <TabsTrigger value='editor' disabled={!hasFile}>
                  Dựng video
                </TabsTrigger>
              </TabsList>

              {/* Processing steps are the main job so they take most of the space; Files is
                  secondary info, placed in a narrow column beside it. */}
              <TabsContent value='pipeline' className='grid gap-6 lg:grid-cols-5'>
              <div className='space-y-6 lg:order-2 lg:col-span-2'>
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

              <div className='space-y-6 lg:order-1 lg:col-span-3'>
                <Card>
                  <CardHeader>
                    <CardTitle className='text-base'>Các bước xử lý</CardTitle>
                    <CardDescription>
                      Pipeline chạy tuần tự — mỗi bước cần kết quả của bước trước.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className='space-y-3'>
                    {steps.map((step) => (
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

              </div>
              </TabsContent>

              <TabsContent value='subtitles'>
                <SubtitleReview
                  videoId={videoId}
                  segments={transcript}
                  hasTranslation={hasTranslation}
                  variant={
                    fileList.some((f) => f.variant === 'burned' && f.exists)
                      ? 'burned'
                      : fileList.some((f) => f.variant === 'dubbed' && f.exists)
                        ? 'dubbed'
                        : 'original'
                  }
                  onEdit={() => setEditorOpen(true)}
                />
              </TabsContent>

              <TabsContent value='voices'>
                <SpeakerVoices
                  videoId={videoId}
                  segments={transcript}
                  speakerVoices={detail?.speaker_voices ?? {}}
                />
              </TabsContent>

              <TabsContent value='editor'>
                <div className='mb-4'>
                  <p className='text-sm text-muted-foreground'>
                    Cắt/sắp xếp lại video, thêm overlay/CTA, chỉnh âm lượng — AI chỉ
                    gợi ý, bạn kéo-chỉnh rồi bấm Render.
                  </p>
                </div>
                {/* Mount only when the tab is open: the editor loads the waveform + video, and should not
                    run in the background while the user is on another tab. */}
                <TimelineEditor subject={{ type: 'video', id: videoId }} />
              </TabsContent>
            </Tabs>

            {/* The dialog should sit outside Tabs: it covers the whole screen and belongs to no tab. */}
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
          </>
        )}
      </Main>
    </>
  )
}
