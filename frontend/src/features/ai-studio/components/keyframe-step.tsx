import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { Check, Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import {
  generateKeyframe,
  generatedAssetFileUrl,
  getCharacterReferences,
  getGeneratedAssets,
  getGenerationCostEstimate,
  type GeneratedAssetRead,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { type StudioSettings } from '../types'

interface Props {
  settings: StudioSettings
  selectedKeyframeId: number | null
  onSelectKeyframe: (assetId: number) => void
}

function parseMentions(prompt: string): string[] {
  const matches = prompt.toLowerCase().match(/@([a-z0-9_]+)/g) ?? []
  return Array.from(new Set(matches.map((m) => m.slice(1))))
}

export function KeyframeStep({ settings, selectedKeyframeId, onSelectKeyframe }: Props) {
  const queryClient = useQueryClient()
  const [prompt, setPrompt] = useState('')

  const references = useQuery({
    queryKey: ['ai-studio', 'character-references'],
    queryFn: getCharacterReferences,
  })
  const images = useQuery({
    queryKey: ['ai-studio', 'assets', 'image'],
    queryFn: () => getGeneratedAssets('image'),
  })
  const estimate = useQuery({
    queryKey: ['ai-studio', 'cost', 'image', settings.imageModel, settings.variantCount],
    queryFn: () =>
      getGenerationCostEstimate({
        asset_type: 'image',
        model: settings.imageModel,
        count: settings.variantCount,
      }),
  })

  const knownNames = new Set((references.data ?? []).map((r) => r.name))
  const mentions = parseMentions(prompt)
  const unknownMentions = mentions.filter((name) => !knownNames.has(name))
  const matchedReferences = (references.data ?? []).filter((r) => mentions.includes(r.name))

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['ai-studio', 'assets'] })
    queryClient.invalidateQueries({ queryKey: ['ai-studio', 'budget'] })
  }

  const generate = useMutation({
    mutationFn: async () => {
      const runs = Array.from({ length: settings.variantCount }, (_, index) =>
        generateKeyframe({
          prompt: settings.variantCount > 1 ? `${prompt} [v${index + 1}]` : prompt,
          model: settings.imageModel,
          output_prefix: settings.outputPrefix || null,
        })
      )
      return Promise.all(runs)
    },
    onSuccess: (results) => {
      invalidate()
      const cached = results.filter((r) => r.from_cache).length
      const first = results[0]?.asset.id
      if (first != null) onSelectKeyframe(first)
      toast.success(
        cached > 0
          ? `Đã sinh ${results.length} ảnh (${cached} dùng lại kết quả cũ, không tốn phí).`
          : `Đã sinh ${results.length} ảnh.`
      )
    },
    onError: (error) => {
      if (!axios.isAxiosError(error)) {
        toast.error('Không sinh được ảnh.')
        return
      }
      const detail = (error.response?.data as { detail?: string })?.detail
      toast.error(detail ?? 'Không sinh được ảnh.')
    },
  })

  const canGenerate = prompt.trim().length > 0 && unknownMentions.length === 0

  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between'>
        <CardTitle className='text-base'>1. Sinh ảnh keyframe</CardTitle>
        {estimate.data && (
          <Badge variant='outline'>
            ~${estimate.data.estimated_cost_usd.toFixed(3)}
          </Badge>
        )}
      </CardHeader>
      <CardContent className='space-y-3'>
        <div className='space-y-1'>
          <Label htmlFor='keyframe-prompt'>Prompt mô tả cảnh</Label>
          <Textarea
            id='keyframe-prompt'
            rows={3}
            placeholder='@ten_nhan_vat medium shot, 50mm, standing at the bank counter...'
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          {references.data && references.data.length > 0 && (
            <p className='text-muted-foreground text-xs'>
              Gọi ảnh tham chiếu bằng{' '}
              {references.data.map((r) => (
                <button
                  key={r.id}
                  type='button'
                  className='text-primary mr-1 underline'
                  onClick={() => setPrompt((current) => `${current}@${r.name} `.trimStart())}
                >
                  @{r.name}
                </button>
              ))}
            </p>
          )}
        </div>

        {matchedReferences.length > 0 && (
          <p className='text-muted-foreground text-xs'>
            Sẽ đính kèm:{' '}
            {matchedReferences.map((r) => `@${r.name} (${r.image_count} ảnh)`).join(', ')}
          </p>
        )}

        {unknownMentions.length > 0 && (
          <p className='text-destructive text-xs'>
            Không có bộ ảnh tên: {unknownMentions.map((n) => `@${n}`).join(', ')} — sửa lại
            hoặc tạo bộ ảnh trước khi sinh.
          </p>
        )}

        <Button
          onClick={() => generate.mutate()}
          disabled={!canGenerate || generate.isPending}
          className='gap-1'
        >
          <Sparkles className='size-3.5' />
          {generate.isPending
            ? 'Đang sinh ảnh...'
            : `Sinh ${settings.variantCount} ảnh${
                estimate.data ? ` — ~$${estimate.data.estimated_cost_usd.toFixed(3)}` : ''
              }`}
        </Button>

        {images.data && images.data.length > 0 && (
          <div className='space-y-2'>
            <p className='text-sm font-medium'>Chọn 1 ảnh để làm keyframe</p>
            <div className='grid grid-cols-2 gap-2 sm:grid-cols-4'>
              {images.data.slice(0, 8).map((asset) => (
                <KeyframeThumb
                  key={asset.id}
                  asset={asset}
                  selected={asset.id === selectedKeyframeId}
                  onSelect={() => onSelectKeyframe(asset.id)}
                />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function KeyframeThumb({
  asset,
  selected,
  onSelect,
}: {
  asset: GeneratedAssetRead
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type='button'
      onClick={onSelect}
      className={`relative overflow-hidden rounded-md border-2 transition ${
        selected ? 'border-primary' : 'border-transparent hover:border-muted-foreground/40'
      }`}
      title={asset.prompt}
    >
      <img
        src={generatedAssetFileUrl(asset.id)}
        alt={asset.prompt.slice(0, 60)}
        className='aspect-video w-full object-cover'
        loading='lazy'
      />
      {selected && (
        <span className='bg-primary text-primary-foreground absolute end-1 top-1 rounded-full p-0.5'>
          <Check className='size-3' />
        </span>
      )}
    </button>
  )
}
