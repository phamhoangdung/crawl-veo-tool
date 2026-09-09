import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Film, Link2, Loader2, Play, Sparkles, Trash2, TriangleAlert } from 'lucide-react'
import { generatedAssetFileUrl, type SceneRead } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { SCENE_NODE_WIDTH } from '../graph'

export interface SceneNodeData extends Record<string, unknown> {
  scene: SceneRead
  isFirst: boolean
  isGenerating: boolean
  onPromptChange: (sceneId: number, prompt: string) => void
  onGenerate: (sceneId: number) => void
  onDelete: (sceneId: number) => void
  onOpenSettings: (sceneId: number) => void
}

const STATUS_BADGE: Record<
  SceneRead['status'],
  { label: string; variant: 'outline' | 'secondary' | 'destructive' }
> = {
  draft: { label: 'Chưa sinh', variant: 'outline' },
  keyframe_ready: { label: 'Có ảnh', variant: 'secondary' },
  clip_ready: { label: 'Có clip', variant: 'secondary' },
  failed: { label: 'Lỗi', variant: 'destructive' },
}

function SceneNodeInner({ data, selected }: NodeProps) {
  const {
    scene,
    isFirst,
    isGenerating,
    onPromptChange,
    onGenerate,
    onDelete,
    onOpenSettings,
  } = data as SceneNodeData
  const status = STATUS_BADGE[scene.status]

  return (
    <div
      className={`bg-card rounded-lg border-2 shadow-sm transition ${
        selected ? 'border-primary' : 'border-border'
      }`}
      style={{ width: SCENE_NODE_WIDTH }}
    >
      {/* Cảnh đầu không nhận cạnh vào — nó không có gì phía trước để nối. */}
      {!isFirst && <Handle type='target' position={Position.Left} />}
      <Handle type='source' position={Position.Right} />
      {/* Handle riêng cho nhân vật — thả cạnh vào đây để tự chèn @tên vào prompt,
          tách khỏi handle Left (nối frame từ cảnh trước) để khỏi lẫn 2 loại cạnh. */}
      <Handle type='target' position={Position.Top} id='character' className='!bg-primary' />

      <div className='flex items-center justify-between gap-1 border-b px-2 py-1.5'>
        <span className='text-sm font-medium'>Cảnh {scene.order_index + 1}</span>
        <div className='flex items-center gap-1'>
          <Badge variant={status.variant} className='text-[10px]'>
            {status.label}
          </Badge>
          <Button
            variant='ghost'
            size='icon'
            className='size-6'
            title='Xoá cảnh'
            onClick={() => onDelete(scene.id)}
          >
            <Trash2 className='size-3' />
          </Button>
        </div>
      </div>

      <div className='space-y-2 p-2'>
        <Textarea
          value={scene.prompt}
          onChange={(e) => onPromptChange(scene.id, e.target.value)}
          placeholder='@nguoique mô tả cảnh...'
          rows={2}
          className='nodrag text-xs'
        />

        <div className='grid grid-cols-2 gap-1.5'>
          <Preview
            assetId={scene.keyframe_asset_id}
            kind='image'
            label='Ảnh keyframe'
          />
          <Preview assetId={scene.clip_asset_id} kind='video' label='Clip' />
        </div>

        <div className='text-muted-foreground flex flex-wrap items-center gap-1 text-[10px]'>
          <span>{scene.duration_seconds}s</span>
          <span>·</span>
          <span>{scene.use_ken_burns ? 'Ảnh tĩnh (miễn phí)' : 'Video AI'}</span>
          {!isFirst && scene.chain_from_previous && (
            <>
              <span>·</span>
              <span className='inline-flex items-center gap-0.5'>
                <Link2 className='size-2.5' />
                nối frame
              </span>
            </>
          )}
          {!isFirst && scene.transition_in === 'fade' && (
            <>
              <span>·</span>
              <span>fade</span>
            </>
          )}
        </div>

        {scene.error && (
          <p className='text-destructive flex items-start gap-1 text-[10px]'>
            <TriangleAlert className='mt-0.5 size-3 shrink-0' />
            <span className='line-clamp-2'>{scene.error}</span>
          </p>
        )}

        <div className='flex gap-1'>
          <Button
            size='sm'
            variant='outline'
            className='nodrag h-7 flex-1 gap-1 text-xs'
            onClick={() => onGenerate(scene.id)}
            disabled={isGenerating}
          >
            {isGenerating ? (
              <Loader2 className='size-3 animate-spin' />
            ) : (
              <Sparkles className='size-3' />
            )}
            {isGenerating ? 'Đang sinh...' : 'Sinh cảnh'}
          </Button>
          <Button
            size='sm'
            variant='ghost'
            className='nodrag h-7 px-2 text-xs'
            onClick={() => onOpenSettings(scene.id)}
          >
            Tuỳ chọn
          </Button>
        </div>
      </div>
    </div>
  )
}

function Preview({
  assetId,
  kind,
  label,
}: {
  assetId: number | null
  kind: 'image' | 'video'
  label: string
}) {
  if (assetId == null) {
    return (
      <div className='bg-muted text-muted-foreground flex aspect-video items-center justify-center rounded text-[10px]'>
        {label}
      </div>
    )
  }

  if (kind === 'image') {
    return (
      <img
        src={generatedAssetFileUrl(assetId)}
        alt={label}
        className='aspect-video w-full rounded object-cover'
        loading='lazy'
      />
    )
  }

  return (
    <a
      href={generatedAssetFileUrl(assetId)}
      target='_blank'
      rel='noreferrer'
      className='nodrag bg-muted hover:bg-muted/70 flex aspect-video items-center justify-center rounded transition'
      title='Mở clip'
    >
      <span className='text-muted-foreground flex items-center gap-1 text-[10px]'>
        <Play className='size-3' />
        <Film className='size-3' />
      </span>
    </a>
  )
}

export const SceneNode = memo(SceneNodeInner)
