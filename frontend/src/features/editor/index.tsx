import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Sparkles, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  API_BASE_URL,
  type ClipCandidate,
  type CropBox,
  createClip,
  getClipCandidates,
  getProject,
  getProjectTimelineSuggestion,
  getSubjectTimeline,
  projectOutputUrl,
  getAudioStems,
  getVideoDetail,
  getWaveform,
  renderSubjectTimeline,
  saveSubjectTimeline,
  type TimelineOperations,
  type TimelineSubject,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { useEditorShortcuts } from '@/hooks/use-editor-shortcuts'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { AssetPanel } from './asset-panel'
import { BlurRegionLayer } from './blur-region-layer'
import { CropBoxSelector } from './crop-box-selector'
import { ImageLayer } from './image-layer'
import { defaultVerticalCrop } from './layout'
import { OverlayLayer } from './overlay-layer'
import { useEditorStore } from './store'
import { SubtitleBoxPanel } from './subtitle-box-panel'
import { Timeline } from './timeline'
import { EditorToolbar } from './toolbar'
import { VolumeMixer } from './volume-mixer'

function formatClipTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

interface TimelineEditorProps {
  /** A crawled video, or a multi-scene project built with AI — the same editor. */
  subject: TimelineSubject
}

/** Build the initial suggested timeline from the existing pipeline (source video + dubbed
 * audio + translated subtitles) — acts as the "AI suggestion" until Phase 9/10/11 have
 * their own suggestion generator per use case. Only fills the state, does NOT save/render
 * automatically — the user clicks "Save" then "Render" separately. */
async function buildSuggestionFromPipeline(
  videoId: number
): Promise<TimelineOperations> {
  const [video, stems] = await Promise.all([
    getVideoDetail(videoId),
    getAudioStems(videoId),
  ])
  const duration = video.duration_seconds ?? 0
  const videoSource = video.local_path

  const tracks: TimelineOperations['tracks'] = []
  if (videoSource) {
    tracks.push({
      type: 'video',
      clips: [{ source: videoSource, start: 0, end: duration }],
    })
  }

  // Split the narration and background music into 2 tracks to adjust volume independently. Only when
  // dubbing has not run (no stems yet) use the pre-mixed version as 1 track.
  if (stems.voice || stems.background) {
    if (stems.voice) {
      tracks.push({
        type: 'audio',
        role: 'voice',
        clips: [
          {
            source: stems.voice,
            start: 0,
            end: duration,
            track_start: 0,
            volume: 1.0,
          },
        ],
      })
    }
    if (stems.background) {
      tracks.push({
        type: 'audio',
        role: 'music',
        clips: [
          // Keep the background music quieter than the narration, otherwise it drowns out the speech.
          {
            source: stems.background,
            start: 0,
            end: duration,
            track_start: 0,
            volume: 0.3,
          },
        ],
      })
    }
  } else {
    const fallback = stems.mixed ?? video.local_path
    if (fallback) {
      tracks.push({
        type: 'audio',
        role: 'voice',
        clips: [
          {
            source: fallback,
            start: 0,
            end: duration,
            track_start: 0,
            volume: 1.0,
          },
        ],
      })
    }
  }
  const captionClips = video.transcript
    .filter((seg) => seg.translated_text?.trim())
    .map((seg) => ({
      text: seg.translated_text,
      start: seg.start,
      end: seg.end,
      x: 0.5,
      y: 0.9,
    }))
  if (captionClips.length > 0) {
    tracks.push({ type: 'overlay', clips: captionClips })
  }

  return { tracks }
}

/** Initial suggestion by subject: a crawled video is built from the pipeline (source +
 * narration + subtitles), while an AI project takes the scene chain straight from the canvas — the backend
 * builds it because only it knows which scenes already have clips. */
async function buildSuggestion(
  subject: TimelineSubject
): Promise<TimelineOperations> {
  if (subject.type === 'video') return buildSuggestionFromPipeline(subject.id)
  return { tracks: await getProjectTimelineSuggestion(subject.id) }
}

export function TimelineEditor({ subject }: TimelineEditorProps) {
  const queryClient = useQueryClient()
  // The features below only make sense for crawled videos: short-clip suggestions,
  // waveform and audio stems are all produced from the translate/dub pipeline, and AI projects
  // have not been through that pipeline so there is nothing to read.
  const isVideo = subject.type === 'video'
  const videoId = subject.id
  const operations = useEditorStore((s) => s.operations)
  const setOperations = useEditorStore((s) => s.setOperations)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const seekRequest = useEditorStore((s) => s.seekRequest)
  const consumeSeek = useEditorStore((s) => s.consumeSeek)
  const [videoDims, setVideoDims] = useState({ width: 0, height: 0 })
  const [selectedCandidate, setSelectedCandidate] =
    useState<ClipCandidate | null>(null)
  const [crop, setCrop] = useState<CropBox | null>(null)
  const [ctaText, setCtaText] = useState('')

  const { data: clipCandidates } = useQuery({
    queryKey: ['clip-candidates', videoId],
    queryFn: () => getClipCandidates(videoId),
    enabled: isVideo,
  })

  function selectCandidate(candidate: ClipCandidate) {
    setSelectedCandidate(candidate)
    if (videoDims.width > 0) {
      setCrop(defaultVerticalCrop(videoDims.width, videoDims.height))
    }
  }

  const createClipMutation = useMutation({
    mutationFn: () => {
      if (!selectedCandidate) throw new Error('Chưa chọn đoạn')
      return createClip(videoId, {
        start: selectedCandidate.start,
        end: selectedCandidate.end,
        crop: crop ?? undefined,
        cta_text: ctaText.trim() || undefined,
      })
    },
    onSuccess: () => toast.success('Đã tạo clip.'),
    onError: () => toast.error('Tạo clip thất bại.'),
  })

  // If no timeline is saved yet, build it straight from the pipeline: the user is already on this
  // video page, making them click one more button to see the content is a needless step.
  // The cache key must include the subject kind: video id=1 and project id=1 are two different
  // things, sharing the key ['timeline', 1] would make opening a project show the
  // video's timeline.
  const { data: savedTracks, isLoading } = useQuery({
    queryKey: ['timeline', subject.type, subject.id],
    queryFn: async () => {
      const saved = await getSubjectTimeline(subject)
      // The backend returns null when no timeline is saved yet (not an empty array).
      if (saved && saved.length > 0) return saved
      const suggested = await buildSuggestion(subject)
      return suggested.tracks
    },
  })

  const { data: videoDetail } = useQuery({
    queryKey: ['video', videoId],
    queryFn: () => getVideoDetail(videoId),
    enabled: isVideo,
  })

  const { data: waveformPeaks } = useQuery({
    queryKey: ['waveform', videoId],
    queryFn: () => getWaveform(videoId),
    retry: false,
    enabled: isVideo,
  })

  useEffect(() => {
    if (savedTracks) setOperations({ tracks: savedTracks })
  }, [savedTracks, setOperations])

  const selected = useEditorStore((s) => s.selected)
  const splitClip = useEditorStore((s) => s.splitClip)
  const duplicateClip = useEditorStore((s) => s.duplicateClip)
  const removeClip = useEditorStore((s) => s.removeClip)
  const undo = useEditorStore((s) => s.undo)
  const redo = useEditorStore((s) => s.redo)

  useEditorShortcuts({
    onTogglePlay: () => {
      const video = videoRef.current
      if (!video) return
      if (video.paused) void video.play()
      else video.pause()
    },
    onSplit: () =>
      selected &&
      splitClip(selected.trackIndex, selected.clipIndex, currentTime),
    onDelete: () =>
      selected && removeClip(selected.trackIndex, selected.clipIndex),
    onDuplicate: () =>
      selected && duplicateClip(selected.trackIndex, selected.clipIndex),
    onUndo: undo,
    onRedo: redo,
    onNudge: (delta) => {
      const video = videoRef.current
      if (!video) return
      video.currentTime = Math.max(0, video.currentTime + delta)
      setCurrentTime(video.currentTime)
    },
  })

  // Selecting a clip on the timeline → seek the preview to the start of that clip. Read the request from the store because
  // the timeline and the <video> tag live in 2 different components.
  useEffect(() => {
    if (!seekRequest) return
    const video = videoRef.current
    if (video) {
      video.currentTime = seekRequest.seconds
      setCurrentTime(seekRequest.seconds)
    }
    consumeSeek()
  }, [seekRequest, consumeSeek])

  const applySuggestion = useMutation({
    mutationFn: () => buildSuggestion(subject),
    onSuccess: (ops) => {
      setOperations(ops)
      toast.success('Đã điền gợi ý — kéo-chỉnh rồi bấm Lưu.')
    },
    onError: () =>
      toast.error(
        isVideo
          ? 'Không tạo được gợi ý (video chưa có đủ dữ liệu?).'
          : 'Không tạo được gợi ý — các cảnh cần có clip trước (sinh ở canvas).'
      ),
  })

  const save = useMutation({
    mutationFn: () => saveSubjectTimeline(subject, operations),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['timeline', subject.type, subject.id],
      })
      toast.success('Đã lưu timeline.')
    },
    onError: () => toast.error('Lưu timeline thất bại.'),
  })

  const render = useMutation({
    mutationFn: () => renderSubjectTimeline(subject),
    onSuccess: () => toast.success('Đã render xong video.'),
    onError: () => toast.error('Render thất bại — kiểm tra lại timeline.'),
  })

  const { data: projectDetail } = useQuery({
    queryKey: ['project', subject.id],
    queryFn: () => getProject(subject.id),
    enabled: !isVideo,
  })

  const hasVideoTrack = operations.tracks.some(
    (t) => t.type === 'video' && t.clips.length > 0
  )

  // Prefer the dubbed version so the narration is audible while drag-editing; a video that is not
  // dubbed plays the original instead of breaking the preview frame entirely.
  const previewVariant = videoDetail?.dubbed_path ? 'dubbed' : 'original'
  // An AI project previews with the rough cut from the canvas: each scene is a separate file, and the
  // browser cannot join them. If there is no rough cut yet there is nothing to play.
  const previewUrl = isVideo
    ? hasVideoTrack
      ? `${API_BASE_URL}/api/library/${videoId}/stream?variant=${previewVariant}`
      : null
    : (projectDetail?.rendered_path ?? null)
      ? projectOutputUrl(subject.id)
      : null

  return (
    <div className='space-y-4'>
      <div className='flex flex-wrap items-center gap-2'>
        <Button
          variant='outline'
          className='gap-1.5'
          disabled={applySuggestion.isPending}
          onClick={() => applySuggestion.mutate()}
        >
          <Sparkles className='size-4' />
          {applySuggestion.isPending ? 'Đang tạo gợi ý...' : 'Dùng gợi ý AI'}
        </Button>
        <Button
          variant='outline'
          disabled={operations.tracks.length === 0 || save.isPending}
          onClick={() => save.mutate()}
        >
          {save.isPending ? 'Đang lưu...' : 'Lưu'}
        </Button>
        <Button
          className='ms-auto'
          disabled={operations.tracks.length === 0 || render.isPending}
          onClick={() => render.mutate()}
        >
          {render.isPending ? 'Đang render...' : 'Render'}
        </Button>
      </div>

      {/* 2 columns on wide screens: the preview frame on the left at exactly the real aspect
          ratio of the video (vertical 9:16 or landscape 16:9 both use all the available height/
          width, no longer pinned to one small width), the tools panel on the
          right always visible side by side — previously a single stacked column forced scrolling
          past the whole preview frame to reach AssetPanel/SubtitleBoxPanel. */}
      <div className='grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem] xl:items-start'>
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>Xem trước</CardTitle>
          </CardHeader>
          <CardContent>
            {/* `width` is computed with min(): the smaller of "fits the column width"
                and "fits 70vh of height converted by the ratio" — so `aspect-ratio` derives
                the other dimension from a width that is CERTAIN (a block box derives height from a
                stable width, the reverse does not — found by measuring with a real vertical video:
                using a flex item or fixed w-full is right for only
                1 of the 2 ratio kinds, not both). This way a landscape video fills the
                column, a vertical video shrinks by height, with no JS measuring. */}
            {(() => {
              const ratio =
                videoDims.width && videoDims.height
                  ? videoDims.width / videoDims.height
                  : 16 / 9
              return (
                <div
                  className='relative mx-auto overflow-hidden rounded-lg bg-black'
                  style={{
                    aspectRatio: ratio,
                    width: `min(100%, calc(70vh * ${ratio}))`,
                  }}
                >
                  {previewUrl ? (
                    <video
                      ref={videoRef}
                      src={previewUrl}
                      controls
                      className='size-full object-contain'
                      onTimeUpdate={(e) =>
                        setCurrentTime(e.currentTarget.currentTime)
                      }
                      onLoadedMetadata={(e) =>
                        setVideoDims({
                          width: e.currentTarget.videoWidth,
                          height: e.currentTarget.videoHeight,
                        })
                      }
                    />
                  ) : (
                    <div className='flex h-48 items-center justify-center text-sm text-muted-foreground'>
                      {isLoading
                        ? 'Đang tải...'
                        : isVideo
                          ? 'Video chưa được tải về máy — chạy bước "Tải video" trước.'
                          : 'Chưa có bản dựng thô — bấm "Dựng video" ở canvas trước, rồi quay lại đây tinh chỉnh.'}
                    </div>
                  )}
                  <OverlayLayer currentTime={currentTime} />
                  <ImageLayer currentTime={currentTime} />
                  <BlurRegionLayer currentTime={currentTime} />
                  {selectedCandidate && crop && (
                    <CropBoxSelector
                      videoWidth={videoDims.width}
                      videoHeight={videoDims.height}
                      value={crop}
                      onChange={setCrop}
                    />
                  )}
                </div>
              )
            })()}

            <div className='mt-4'>
              <VolumeMixer />
            </div>
          </CardContent>
        </Card>

        {/* Sticky on wide screens: scrolling down the page to see the Timeline still shows the
            tools panel, without losing the clip being adjusted in the ClipInspector. */}
        <div className='space-y-4 xl:sticky xl:top-4'>
          <AssetPanel />
          <SubtitleBoxPanel />
          <ClipInspector />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className='text-base'>Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <EditorToolbar currentTime={currentTime} />
          <div className='mt-3'>
            <Timeline waveformPeaks={waveformPeaks} currentTime={currentTime} />
          </div>
        </CardContent>
      </Card>

      {/* Short-clip suggestions come from the translated transcript of a crawled video — AI projects
          have no transcript so it is hidden entirely instead of showing a card that is always empty. */}
      {isVideo && (
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>
              Cắt clip ngắn (TikTok/Shorts)
            </CardTitle>
            <CardDescription>
              Gợi ý đoạn nổi bật từ transcript chỉ để tham khảo thứ tự — không
              tự chọn/loại bỏ thay bạn, tự chọn đoạn ưng ý rồi kéo khung crop
              trên khung preview phía trên.
            </CardDescription>
          </CardHeader>
          <CardContent className='space-y-3'>
            {!clipCandidates || clipCandidates.length === 0 ? (
              <p className='text-sm text-muted-foreground'>
                Chưa có gợi ý — cần phụ đề đã dịch trước.
              </p>
            ) : (
              <div className='flex flex-col gap-2'>
                {clipCandidates.map((candidate, i) => (
                  <button
                    key={i}
                    type='button'
                    onClick={() => selectCandidate(candidate)}
                    className={cn(
                      'rounded-md border p-2 text-start text-xs hover:bg-muted/60',
                      selectedCandidate === candidate &&
                        'border-primary bg-primary/5'
                    )}
                  >
                    <span className='font-medium'>
                      {formatClipTime(candidate.start)} →{' '}
                      {formatClipTime(candidate.end)}
                    </span>
                    <p className='line-clamp-2 text-muted-foreground'>
                      {candidate.text}
                    </p>
                  </button>
                ))}
              </div>
            )}

            {selectedCandidate && (
              <div className='flex flex-wrap items-end gap-2'>
                <div className='min-w-48 flex-1 space-y-1'>
                  <Label className='text-xs'>Text CTA (tuỳ chọn)</Label>
                  <Input
                    value={ctaText}
                    onChange={(e) => setCtaText(e.target.value)}
                    placeholder='Xem full tại YouTube: ...'
                  />
                </div>
                <Button
                  disabled={createClipMutation.isPending}
                  onClick={() => createClipMutation.mutate()}
                >
                  {createClipMutation.isPending
                    ? 'Đang tạo clip...'
                    : 'Tạo clip'}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

/** Detail panel for the selected clip — enter exact numbers instead of only dragging with
 * the mouse (the mouse is error-prone at small time marks). */
function ClipInspector() {
  const selected = useEditorStore((s) => s.selected)
  const operations = useEditorStore((s) => s.operations)
  const updateClip = useEditorStore((s) => s.updateClip)
  const removeClip = useEditorStore((s) => s.removeClip)

  if (!selected) return null
  const track = operations.tracks[selected.trackIndex]
  const clip = track?.clips[selected.clipIndex]
  if (!track || !clip) return null

  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between'>
        <CardTitle className='text-base'>
          Chi tiết clip đang chọn ({track.type})
        </CardTitle>
        <Button
          size='icon'
          variant='ghost'
          className='size-7 text-muted-foreground hover:text-destructive'
          title='Xoá clip'
          onClick={() => removeClip(selected.trackIndex, selected.clipIndex)}
        >
          <Trash2 className='size-3.5' />
        </Button>
      </CardHeader>
      <CardContent className='flex flex-wrap gap-3'>
        <div className='space-y-1'>
          <Label className='text-xs'>Bắt đầu (giây)</Label>
          <Input
            type='number'
            step='0.1'
            className='w-24'
            value={clip.start}
            onChange={(e) =>
              updateClip(selected.trackIndex, selected.clipIndex, {
                start: Number(e.target.value),
              })
            }
          />
        </div>
        <div className='space-y-1'>
          <Label className='text-xs'>Kết thúc (giây)</Label>
          <Input
            type='number'
            step='0.1'
            className='w-24'
            value={clip.end}
            onChange={(e) =>
              updateClip(selected.trackIndex, selected.clipIndex, {
                end: Number(e.target.value),
              })
            }
          />
        </div>
        {track.type === 'audio' && (
          <div className='space-y-1'>
            <Label className='text-xs'>Âm lượng</Label>
            <Input
              type='number'
              step='0.1'
              min={0}
              max={2}
              className='w-24'
              value={clip.volume ?? 1}
              onChange={(e) =>
                updateClip(selected.trackIndex, selected.clipIndex, {
                  volume: Number(e.target.value),
                })
              }
            />
          </div>
        )}
        {track.type === 'overlay' && (
          <div className='min-w-48 flex-1 space-y-1'>
            <Label className='text-xs'>Nội dung</Label>
            <Input
              value={clip.text ?? ''}
              onChange={(e) =>
                updateClip(selected.trackIndex, selected.clipIndex, {
                  text: e.target.value,
                })
              }
            />
          </div>
        )}
        {track.type === 'image' && (
          <div className='space-y-1'>
            <Label className='text-xs'>Độ mờ (0-1)</Label>
            <Input
              type='number'
              step='0.05'
              min={0}
              max={1}
              className='w-24'
              value={clip.opacity ?? 1}
              onChange={(e) =>
                updateClip(selected.trackIndex, selected.clipIndex, {
                  opacity: Number(e.target.value),
                })
              }
            />
          </div>
        )}
        {track.type === 'blur' && (
          <>
            <div className='space-y-1'>
              <Label className='text-xs'>Kiểu che</Label>
              <select
                className='h-9 w-32 rounded-md border bg-transparent px-2 text-sm'
                value={clip.mode ?? 'blur'}
                onChange={(e) =>
                  updateClip(selected.trackIndex, selected.clipIndex, {
                    mode: e.target.value as 'blur' | 'pixelate',
                  })
                }
              >
                <option value='blur'>Làm nhoè</option>
                <option value='pixelate'>Ô vuông (che chữ tốt hơn)</option>
              </select>
            </div>
            <div className='space-y-1'>
              <Label className='text-xs'>Độ mạnh</Label>
              <Input
                type='number'
                step='1'
                min={1}
                className='w-24'
                value={clip.strength ?? 20}
                onChange={(e) =>
                  updateClip(selected.trackIndex, selected.clipIndex, {
                    strength: Number(e.target.value),
                  })
                }
              />
            </div>
          </>
        )}
        {track.type === 'video' && (
          <div className='space-y-1'>
            <Label className='text-xs'>Chuyển cảnh với clip trước</Label>
            <select
              className='h-9 w-28 rounded-md border bg-transparent px-2 text-sm'
              value={clip.transition_in ?? 'cut'}
              onChange={(e) =>
                updateClip(selected.trackIndex, selected.clipIndex, {
                  transition_in: e.target.value as 'cut' | 'fade',
                })
              }
            >
              <option value='cut'>Cắt cứng</option>
              <option value='fade'>Fade</option>
            </select>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
