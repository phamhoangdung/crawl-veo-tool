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
  getTimeline,
  getVideoDetail,
  getWaveform,
  renderTimeline,
  saveTimeline,
  type TimelineOperations,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { CropBoxSelector } from './crop-box-selector'
import { defaultVerticalCrop } from './layout'
import { OverlayLayer } from './overlay-layer'
import { useEditorStore } from './store'
import { Timeline } from './timeline'

function formatClipTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

interface TimelineEditorProps {
  videoId: number
}

/** Dựng timeline gợi ý ban đầu từ pipeline đã có (video gốc + audio đã lồng
 * tiếng + phụ đề đã dịch) — đóng vai trò "gợi ý AI" cho tới khi Phase 9/10/11 có
 * bộ sinh gợi ý riêng theo từng use-case. Chỉ điền vào state, KHÔNG lưu/render tự
 * động — người dùng bấm "Lưu" rồi "Render" riêng. */
async function buildSuggestionFromPipeline(videoId: number): Promise<TimelineOperations> {
  const video = await getVideoDetail(videoId)
  const duration = video.duration_seconds ?? 0
  const videoSource = video.local_path
  const voiceSource = video.dubbed_path ?? video.local_path

  const tracks: TimelineOperations['tracks'] = []
  if (videoSource) {
    tracks.push({ type: 'video', clips: [{ source: videoSource, start: 0, end: duration }] })
  }
  if (voiceSource) {
    tracks.push({
      type: 'audio',
      role: 'voice',
      clips: [{ source: voiceSource, start: 0, end: duration, track_start: 0, volume: 1.0 }],
    })
  }
  const captionClips = video.transcript
    .filter((seg) => seg.translated_text?.trim())
    .map((seg) => ({ text: seg.translated_text, start: seg.start, end: seg.end, x: 0.5, y: 0.9 }))
  if (captionClips.length > 0) {
    tracks.push({ type: 'overlay', clips: captionClips })
  }

  return { tracks }
}

export function TimelineEditor({ videoId }: TimelineEditorProps) {
  const queryClient = useQueryClient()
  const operations = useEditorStore((s) => s.operations)
  const setOperations = useEditorStore((s) => s.setOperations)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [videoDims, setVideoDims] = useState({ width: 0, height: 0 })
  const [selectedCandidate, setSelectedCandidate] = useState<ClipCandidate | null>(null)
  const [crop, setCrop] = useState<CropBox | null>(null)
  const [ctaText, setCtaText] = useState('')

  const { data: clipCandidates } = useQuery({
    queryKey: ['clip-candidates', videoId],
    queryFn: () => getClipCandidates(videoId),
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

  const { data: savedTracks, isLoading } = useQuery({
    queryKey: ['timeline', videoId],
    queryFn: () => getTimeline(videoId),
  })

  const { data: waveformPeaks } = useQuery({
    queryKey: ['waveform', videoId],
    queryFn: () => getWaveform(videoId),
    retry: false,
  })

  useEffect(() => {
    if (savedTracks) setOperations({ tracks: savedTracks })
  }, [savedTracks, setOperations])

  const applySuggestion = useMutation({
    mutationFn: () => buildSuggestionFromPipeline(videoId),
    onSuccess: (ops) => {
      setOperations(ops)
      toast.success('Đã điền gợi ý — kéo-chỉnh rồi bấm Lưu.')
    },
    onError: () => toast.error('Không tạo được gợi ý (video chưa có đủ dữ liệu?).'),
  })

  const save = useMutation({
    mutationFn: () => saveTimeline(videoId, operations),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['timeline', videoId] })
      toast.success('Đã lưu timeline.')
    },
    onError: () => toast.error('Lưu timeline thất bại.'),
  })

  const render = useMutation({
    mutationFn: () => renderTimeline(videoId),
    onSuccess: () => toast.success('Đã render xong video.'),
    onError: () => toast.error('Render thất bại — kiểm tra lại timeline.'),
  })

  const previewSource = operations.tracks.find((t) => t.type === 'video')?.clips[0]?.source

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

      <Card>
        <CardHeader>
          <CardTitle className='text-base'>Xem trước</CardTitle>
        </CardHeader>
        <CardContent>
          <div className='relative mx-auto w-full max-w-md overflow-hidden rounded-lg bg-black'>
            {previewSource ? (
              <video
                ref={videoRef}
                src={`${API_BASE_URL}/api/library/${videoId}/stream?variant=dubbed`}
                controls
                className='w-full'
                onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                onLoadedMetadata={(e) =>
                  setVideoDims({
                    width: e.currentTarget.videoWidth,
                    height: e.currentTarget.videoHeight,
                  })
                }
              />
            ) : (
              <div className='flex h-48 items-center justify-center text-sm text-muted-foreground'>
                {isLoading ? 'Đang tải...' : 'Chưa có video — bấm "Dùng gợi ý AI" để bắt đầu.'}
              </div>
            )}
            <OverlayLayer currentTime={currentTime} />
            {selectedCandidate && crop && (
              <CropBoxSelector
                videoWidth={videoDims.width}
                videoHeight={videoDims.height}
                value={crop}
                onChange={setCrop}
              />
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className='text-base'>Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <Timeline waveformPeaks={waveformPeaks} />
        </CardContent>
      </Card>

      <ClipInspector />

      <Card>
        <CardHeader>
          <CardTitle className='text-base'>Cắt clip ngắn (TikTok/Shorts)</CardTitle>
          <CardDescription>
            Gợi ý đoạn nổi bật từ transcript chỉ để tham khảo thứ tự — không tự chọn/loại bỏ
            thay bạn, tự chọn đoạn ưng ý rồi kéo khung crop trên khung preview phía trên.
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
                    selectedCandidate === candidate && 'border-primary bg-primary/5'
                  )}
                >
                  <span className='font-medium'>
                    {formatClipTime(candidate.start)} → {formatClipTime(candidate.end)}
                  </span>
                  <p className='line-clamp-2 text-muted-foreground'>{candidate.text}</p>
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
                {createClipMutation.isPending ? 'Đang tạo clip...' : 'Tạo clip'}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

/** Bảng chỉnh chi tiết clip đang chọn — nhập số chính xác thay vì chỉ kéo bằng
 * chuột (chuột dễ sai số ở mốc thời gian nhỏ). */
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
        <CardTitle className='text-base'>Chi tiết clip đang chọn ({track.type})</CardTitle>
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
              updateClip(selected.trackIndex, selected.clipIndex, { start: Number(e.target.value) })
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
              updateClip(selected.trackIndex, selected.clipIndex, { end: Number(e.target.value) })
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
                updateClip(selected.trackIndex, selected.clipIndex, { text: e.target.value })
              }
            />
          </div>
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
