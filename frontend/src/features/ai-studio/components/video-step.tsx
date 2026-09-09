import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { Clapperboard, Film } from 'lucide-react'
import { toast } from 'sonner'
import {
  exportGeneratedAssetToLibrary,
  generateKenBurnsClip,
  generateVideoClip,
  generatedAssetFileUrl,
  getGeneratedAssets,
  getGenerationCostEstimate,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import {
  KEN_BURNS_MOTIONS,
  VIDEO_DURATIONS,
  VIDEO_MODELS,
  type StudioSettings,
} from '../types'

type Approach = 'ken_burns' | 'ai_video'

interface Props {
  settings: StudioSettings
  selectedKeyframeId: number | null
}

export function VideoStep({ settings, selectedKeyframeId }: Props) {
  const queryClient = useQueryClient()
  const [approach, setApproach] = useState<Approach>('ken_burns')
  const [prompt, setPrompt] = useState('')
  const [duration, setDuration] = useState(5)
  const [motion, setMotion] = useState('zoom_in')
  const [videoModel, setVideoModel] = useState(settings.videoModel)
  const [endKeyframeId, setEndKeyframeId] = useState<number | null>(null)
  const [pendingConfirm, setPendingConfirm] = useState<string | null>(null)

  const images = useQuery({
    queryKey: ['ai-studio', 'assets', 'image'],
    queryFn: () => getGeneratedAssets('image'),
  })
  const videos = useQuery({
    queryKey: ['ai-studio', 'assets', 'video'],
    queryFn: () => getGeneratedAssets('video'),
  })
  const estimate = useQuery({
    queryKey: ['ai-studio', 'cost', 'video', videoModel, duration],
    queryFn: () =>
      getGenerationCostEstimate({
        asset_type: 'video',
        model: videoModel,
        duration_seconds: duration,
      }),
    enabled: approach === 'ai_video',
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['ai-studio', 'assets'] })
    queryClient.invalidateQueries({ queryKey: ['ai-studio', 'budget'] })
  }

  const handleError = (error: unknown) => {
    if (!axios.isAxiosError(error)) {
      toast.error('Không tạo được video.')
      return
    }
    const detail = (error.response?.data as { detail?: string })?.detail
    // 409 = vượt ngưỡng mỗi lần gọi, người dùng có thể xác nhận để tiếp tục.
    if (error.response?.status === 409) {
      setPendingConfirm(detail ?? 'Lần sinh này vượt ngưỡng chi phí.')
      return
    }
    toast.error(detail ?? 'Không tạo được video.')
  }

  const kenBurns = useMutation({
    mutationFn: () =>
      generateKenBurnsClip({
        keyframe_asset_id: selectedKeyframeId!,
        duration_seconds: duration,
        motion,
        output_prefix: settings.outputPrefix || null,
      }),
    onSuccess: () => {
      invalidate()
      toast.success('Đã tạo clip từ ảnh tĩnh — miễn phí.')
    },
    onError: handleError,
  })

  const aiVideo = useMutation({
    mutationFn: (confirmExpensive: boolean) =>
      generateVideoClip({
        prompt,
        keyframe_start_asset_id: selectedKeyframeId!,
        keyframe_end_asset_id: endKeyframeId,
        model: videoModel,
        duration_seconds: duration,
        output_prefix: settings.outputPrefix || null,
        confirm_expensive: confirmExpensive,
      }),
    onSuccess: (result) => {
      invalidate()
      setPendingConfirm(null)
      toast.success(
        result.from_cache
          ? 'Dùng lại clip đã sinh trước đó — không tốn phí.'
          : `Đã sinh clip ${result.asset.duration_seconds}s.`
      )
    },
    onError: handleError,
  })

  const exportToLibrary = useMutation({
    mutationFn: exportGeneratedAssetToLibrary,
    onSuccess: (result) => {
      toast.success(
        `Đã thêm "${result.name}" vào kho dùng chung — chọn được trong Timeline Editor.`
      )
    },
    onError: handleError,
  })

  const busy = kenBurns.isPending || aiVideo.isPending
  const noKeyframe = selectedKeyframeId == null
  const latestVideo = videos.data?.[0]

  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between'>
        <CardTitle className='text-base'>2. Tạo clip</CardTitle>
        {approach === 'ai_video' && estimate.data && (
          <Badge variant={estimate.data.estimated_cost_usd > 1 ? 'destructive' : 'outline'}>
            ~${estimate.data.estimated_cost_usd.toFixed(2)}
          </Badge>
        )}
        {approach === 'ken_burns' && <Badge variant='outline'>Miễn phí</Badge>}
      </CardHeader>
      <CardContent className='space-y-3'>
        {noKeyframe && (
          <p className='text-muted-foreground text-sm'>
            Chọn 1 ảnh keyframe ở bước 1 trước.
          </p>
        )}

        <div className='grid gap-2 sm:grid-cols-2'>
          <ApproachOption
            active={approach === 'ken_burns'}
            onClick={() => setApproach('ken_burns')}
            icon={<Film className='size-4' />}
            title='Ảnh tĩnh + chuyển động camera'
            detail='Miễn phí (ffmpeg). Đủ cho cảnh người nói, cảnh nền.'
          />
          <ApproachOption
            active={approach === 'ai_video'}
            onClick={() => setApproach('ai_video')}
            icon={<Clapperboard className='size-4' />}
            title='Sinh video AI'
            detail='Tốn phí. Cần khi nhân vật cử động hoặc chuyển cảnh phức tạp.'
          />
        </div>

        <div className='grid gap-3 sm:grid-cols-2'>
          <div className='space-y-1'>
            <Label htmlFor='clip-duration'>Thời lượng</Label>
            <Select
              value={String(duration)}
              onValueChange={(value) => setDuration(Number(value))}
            >
              <SelectTrigger id='clip-duration'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {VIDEO_DURATIONS.map((seconds) => (
                  <SelectItem key={seconds} value={String(seconds)}>
                    {seconds}s
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {approach === 'ken_burns' ? (
            <div className='space-y-1'>
              <Label htmlFor='clip-motion'>Kiểu chuyển động</Label>
              <Select value={motion} onValueChange={setMotion}>
                <SelectTrigger id='clip-motion'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {KEN_BURNS_MOTIONS.map((option) => (
                    <SelectItem key={option.id} value={option.id}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : (
            <div className='space-y-1'>
              <Label htmlFor='clip-model'>Model video</Label>
              <Select value={videoModel} onValueChange={setVideoModel}>
                <SelectTrigger id='clip-model'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {VIDEO_MODELS.map((model) => (
                    <SelectItem key={model.id} value={model.id}>
                      {model.label} — ${model.pricePerSecond.toFixed(2)}/s
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        {approach === 'ai_video' && (
          <>
            <div className='space-y-1'>
              <Label htmlFor='clip-prompt'>Prompt chuyển động</Label>
              <Textarea
                id='clip-prompt'
                rows={2}
                placeholder='camera pushes in slowly, she turns her head...'
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />
            </div>

            <div className='space-y-1'>
              <Label htmlFor='clip-end-frame'>Ảnh cuối (tuỳ chọn)</Label>
              <Select
                value={endKeyframeId == null ? 'none' : String(endKeyframeId)}
                onValueChange={(value) =>
                  setEndKeyframeId(value === 'none' ? null : Number(value))
                }
              >
                <SelectTrigger id='clip-end-frame'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='none'>Không dùng (chỉ ảnh đầu)</SelectItem>
                  {(images.data ?? [])
                    .filter((asset) => asset.id !== selectedKeyframeId)
                    .slice(0, 8)
                    .map((asset) => (
                      <SelectItem key={asset.id} value={String(asset.id)}>
                        #{asset.id} — {asset.prompt.slice(0, 40)}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
              <p className='text-muted-foreground text-xs'>
                Có ảnh cuối thì model nội suy chuyển động giữa 2 ảnh — kiểm soát tốt hơn để
                clip khớp cảnh trước/sau.
              </p>
            </div>
          </>
        )}

        <Button
          onClick={() =>
            approach === 'ken_burns' ? kenBurns.mutate() : aiVideo.mutate(false)
          }
          disabled={
            noKeyframe ||
            busy ||
            (approach === 'ai_video' && prompt.trim().length === 0)
          }
          className='gap-1'
        >
          {busy
            ? 'Đang tạo clip...'
            : approach === 'ken_burns'
              ? 'Tạo clip miễn phí'
              : `Sinh video${
                  estimate.data ? ` — ~$${estimate.data.estimated_cost_usd.toFixed(2)}` : ''
                }`}
        </Button>

        {aiVideo.isPending && (
          <p className='text-muted-foreground text-xs'>
            Sinh video thật mất khoảng 1-5 phút. Có thể rời trang, job vẫn chạy.
          </p>
        )}

        {latestVideo && (
          <div className='space-y-1'>
            <p className='text-sm font-medium'>Clip mới nhất</p>
            <video
              key={latestVideo.id}
              src={generatedAssetFileUrl(latestVideo.id)}
              controls
              className='max-h-72 w-full rounded-md border bg-black object-contain'
            />
            <div className='flex items-center justify-between gap-2'>
              <p className='text-muted-foreground text-xs'>
                #{latestVideo.id} · {latestVideo.provider} · {latestVideo.duration_seconds}s ·{' '}
                {latestVideo.cost_estimate_usd === 0
                  ? 'miễn phí'
                  : `$${latestVideo.cost_estimate_usd.toFixed(2)}`}
              </p>
              <Button
                variant='outline'
                size='sm'
                onClick={() => exportToLibrary.mutate(latestVideo.id)}
                disabled={exportToLibrary.isPending}
              >
                {exportToLibrary.isPending ? 'Đang thêm...' : 'Thêm vào kho để ghép'}
              </Button>
            </div>
          </div>
        )}
      </CardContent>

      <Dialog
        open={pendingConfirm != null}
        onOpenChange={(open) => !open && setPendingConfirm(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Xác nhận chi phí</DialogTitle>
            <DialogDescription>{pendingConfirm}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant='outline' onClick={() => setPendingConfirm(null)}>
              Huỷ
            </Button>
            <Button onClick={() => aiVideo.mutate(true)} disabled={aiVideo.isPending}>
              Vẫn tiếp tục
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

function ApproachOption({
  active,
  onClick,
  icon,
  title,
  detail,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  title: string
  detail: string
}) {
  return (
    <button
      type='button'
      onClick={onClick}
      className={`rounded-md border-2 p-2 text-start transition ${
        active ? 'border-primary' : 'hover:border-muted-foreground/40'
      }`}
    >
      <span className='flex items-center gap-1.5 text-sm font-medium'>
        {icon}
        {title}
      </span>
      <span className='text-muted-foreground mt-0.5 block text-xs'>{detail}</span>
    </button>
  )
}
