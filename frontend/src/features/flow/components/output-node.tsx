import { memo } from 'react'
import { Handle, Position } from '@xyflow/react'
import { Clapperboard, Download, FolderInput, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SCENE_NODE_WIDTH } from '../graph'

export interface OutputNodeData extends Record<string, unknown> {
  isRendering: boolean
  hasOutput: boolean
  canRender: boolean
  blockingReason: string | null
  estimatedCostUsd: number | null
  freeScenes: number
  /** Số cảnh chưa có clip — 0 nghĩa là dựng lại chỉ ghép, không tốn phí. */
  pendingScenes: number
  isExporting: boolean
  onRender: () => void
  onOpenOutput: () => void
  onExportToLibrary: () => void
}

function OutputNodeInner({ data }: { data: OutputNodeData }) {
  const {
    isRendering,
    hasOutput,
    canRender,
    blockingReason,
    estimatedCostUsd,
    freeScenes,
    pendingScenes,
    isExporting,
    onRender,
    onOpenOutput,
    onExportToLibrary,
  } = data

  return (
    <div
      className='bg-card rounded-lg border-2 border-dashed p-2 shadow-sm'
      style={{ width: SCENE_NODE_WIDTH, minWidth: SCENE_NODE_WIDTH }}
    >
      <Handle type='target' position={Position.Left} />

      <div className='mb-2 flex items-center gap-1.5 text-sm font-medium'>
        <Clapperboard className='size-4' />
        Video hoàn chỉnh
      </div>

      {blockingReason && (
        <p className='text-muted-foreground mb-2 text-[10px]'>{blockingReason}</p>
      )}

      {estimatedCostUsd !== null && (
        <p className='mb-2 text-[10px]'>
          {pendingScenes === 0 ? (
            // Mọi cảnh đã có clip: dựng lại chỉ ghép, không sinh gì nên không tốn phí.
            <span className='text-muted-foreground'>
              Mọi cảnh đã có clip — dựng lại không tốn phí.
            </span>
          ) : estimatedCostUsd === 0 ? (
            <span className='text-muted-foreground'>
              Miễn phí — {freeScenes} cảnh dùng ảnh tĩnh.
            </span>
          ) : (
            <span
              className={estimatedCostUsd > 1 ? 'text-destructive' : 'text-muted-foreground'}
            >
              Ước tính ~${estimatedCostUsd.toFixed(2)}
              {freeScenes > 0 ? ` (${freeScenes} cảnh miễn phí)` : ''}
            </span>
          )}
        </p>
      )}

      <div className='space-y-1.5'>
        <Button
          size='sm'
          className='nodrag h-7 w-full gap-1 text-xs'
          onClick={onRender}
          disabled={!canRender || isRendering}
        >
          {isRendering ? <Loader2 className='size-3 animate-spin' /> : null}
          {isRendering ? 'Đang dựng...' : 'Dựng video'}
        </Button>

        {hasOutput && (
          <>
            <Button
              size='sm'
              variant='outline'
              className='nodrag h-7 w-full gap-1 text-xs'
              onClick={onOpenOutput}
            >
              <Download className='size-3' />
              Xem / tải video
            </Button>
            <Button
              size='sm'
              variant='outline'
              className='nodrag h-7 w-full gap-1 text-xs'
              onClick={onExportToLibrary}
              disabled={isExporting}
              title='Đưa vào kho để thêm lồng tiếng/phụ đề ở Timeline Editor'
            >
              <FolderInput className='size-3' />
              {isExporting ? 'Đang thêm...' : 'Thêm vào kho'}
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

export const OutputNode = memo(OutputNodeInner)
