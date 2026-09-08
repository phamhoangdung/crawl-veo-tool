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
  getAudioStems,
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
import { AssetPanel } from './asset-panel'
import { CropBoxSelector } from './crop-box-selector'
import { defaultVerticalCrop } from './layout'
import { OverlayLayer } from './overlay-layer'
import { EditorToolbar } from './toolbar'
import { VolumeMixer } from './volume-mixer'
import { useEditorShortcuts } from '@/hooks/use-editor-shortcuts'
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
  const [video, stems] = await Promise.all([
    getVideoDetail(videoId),
    getAudioStems(videoId),
  ])
  const duration = video.duration_seconds ?? 0
  const videoSource = video.local_path

  const tracks: TimelineOperations['tracks'] = []
  if (videoSource) {
    tracks.push({ type: 'video', clips: [{ source: videoSource, start: 0, end: duration }] })
  }

  // Tách giọng đọc và nhạc nền thành 2 track để chỉnh âm lượng riêng. Chỉ khi
  // chưa chạy lồng tiếng (chưa có stem) mới dùng bản trộn sẵn làm 1 track.
  if (stems.voice || stems.background) {
    if (stems.voice) {
      tracks.push({
        type: 'audio',
        role: 'voice',
        clips: [{ source: stems.voice, start: 0, end: duration, track_start: 0, volume: 1.0 }],
      })
    }
    if (stems.background) {
      tracks.push({
        type: 'audio',
        role: 'music',
        clips: [
          // Nhạc nền để nhỏ hơn giọng đọc, nếu không sẽ át lời.
          { source: stems.background, start: 0, end: duration, track_start: 0, volume: 0.3 },
        ],
      })
    }
  } else {
    const fallback = stems.mixed ?? video.local_path
    if (fallback) {
      tracks.push({
        type: 'audio',
        role: 'voice',
        clips: [{ source: fallback, start: 0, end: duration, track_start: 0, volume: 1.0 }],
      })
    }
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
  const seekRequest = useEditorStore((s) => s.seekRequest)
  const consumeSeek = useEditorStore((s) => s.consumeSeek)
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

  // Chưa lưu timeline nào thì dựng luôn từ pipeline: người dùng đã ở trang
  // video này rồi, bắt bấm thêm một nút mới thấy nội dung là bước thừa.
  const { data: savedTracks, isLoading } = useQuery({
    queryKey: ['timeline', videoId],
    queryFn: async () => {
      const saved = await getTimeline(videoId)
      // Backend trả null khi chưa lưu timeline nào (không phải mảng rỗng).
      if (saved && saved.length > 0) return saved
      const suggested = await buildSuggestionFromPipeline(videoId)
      return suggested.tracks
    },
  })

  const { data: videoDetail } = useQuery({
    queryKey: ['video', videoId],
    queryFn: () => getVideoDetail(videoId),
  })

  const { data: waveformPeaks } = useQuery({
    queryKey: ['waveform', videoId],
    queryFn: () => getWaveform(videoId),
    retry: false,
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
    onSplit: () => selected && splitClip(selected.trackIndex, selected.clipIndex, currentTime),
    onDelete: () => selected && removeClip(selected.trackIndex, selected.clipIndex),
    onDuplicate: () => selected && duplicateClip(selected.trackIndex, selected.clipIndex),
    onUndo: undo,
    onRedo: redo,
    onNudge: (delta) => {
      const video = videoRef.current
      if (!video) return
      video.currentTime = Math.max(0, video.currentTime + delta)
      setCurrentTime(video.currentTime)
    },
  })

  // Chọn clip ở timeline → tua preview tới đầu clip đó. Đọc yêu cầu từ store vì
  // timeline và thẻ <video> nằm ở 2 component khác nhau.
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

  // Ưu tiên bản đã lồng tiếng để nghe được giọng đọc khi kéo-chỉnh; video chưa
  // dub thì phát bản gốc thay vì hỏng hẳn khung preview.
  const previewVariant = videoDetail?.dubbed_path ? 'dubbed' : 'original'

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
                src={`${API_BASE_URL}/api/library/${videoId}/stream?variant=${previewVariant}`}
                controls
                className='max-h-[55vh] w-full object-contain'
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
                {isLoading
                  ? 'Đang tải...'
                  : 'Video chưa được tải về máy — chạy bước "Tải video" trước.'}
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

          <div className='mx-auto mt-4 w-full max-w-md'>
            <VolumeMixer />
          </div>
        </CardContent>
      </Card>

      <AssetPanel />

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
