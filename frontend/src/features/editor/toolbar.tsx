import {
  ChevronLeft,
  ChevronRight,
  Copy,
  Redo2,
  Scissors,
  Trash2,
  Undo2,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { MAX_PX_PER_SECOND, MIN_PX_PER_SECOND } from './layout'
import { useEditorStore } from './store'

const ZOOM_FACTOR = 1.5

/**
 * Thanh công cụ timeline: undo/redo, zoom, và các thao tác trên clip đang chọn.
 * Thao tác cần biết vị trí playhead (cắt đôi) nhận `currentTime` từ preview.
 */
export function EditorToolbar({ currentTime }: { currentTime: number }) {
  const selected = useEditorStore((s) => s.selected)
  const operations = useEditorStore((s) => s.operations)
  const pxPerSecond = useEditorStore((s) => s.pxPerSecond)
  const setZoom = useEditorStore((s) => s.setZoom)
  const undo = useEditorStore((s) => s.undo)
  const redo = useEditorStore((s) => s.redo)
  const canUndo = useEditorStore((s) => s.past.length > 0)
  const canRedo = useEditorStore((s) => s.future.length > 0)
  const splitClip = useEditorStore((s) => s.splitClip)
  const duplicateClip = useEditorStore((s) => s.duplicateClip)
  const moveClip = useEditorStore((s) => s.moveClip)
  const removeClip = useEditorStore((s) => s.removeClip)

  const track = selected ? operations.tracks[selected.trackIndex] : null
  const hasSelection = Boolean(selected && track)
  // Đổi thứ tự chỉ có nghĩa với track video (vị trí suy ra từ thứ tự mảng);
  // audio/overlay đã có track_start/start riêng nên kéo trực tiếp là đủ.
  const canReorder = hasSelection && track?.type === 'video' && track.clips.length > 1

  return (
    <div className='flex flex-wrap items-center gap-1'>
      <Button
        size='icon'
        variant='ghost'
        className='size-8'
        title='Hoàn tác (Ctrl+Z)'
        disabled={!canUndo}
        onClick={undo}
      >
        <Undo2 className='size-4' />
      </Button>
      <Button
        size='icon'
        variant='ghost'
        className='size-8'
        title='Làm lại (Ctrl+Shift+Z)'
        disabled={!canRedo}
        onClick={redo}
      >
        <Redo2 className='size-4' />
      </Button>

      <Separator orientation='vertical' className='mx-1 h-6' />

      <Button
        size='icon'
        variant='ghost'
        className='size-8'
        title='Thu nhỏ timeline'
        disabled={pxPerSecond <= MIN_PX_PER_SECOND}
        onClick={() => setZoom(pxPerSecond / ZOOM_FACTOR)}
      >
        <ZoomOut className='size-4' />
      </Button>
      <span className='w-14 text-center text-xs tabular-nums text-muted-foreground'>
        {Math.round(pxPerSecond)}px/s
      </span>
      <Button
        size='icon'
        variant='ghost'
        className='size-8'
        title='Phóng to timeline'
        disabled={pxPerSecond >= MAX_PX_PER_SECOND}
        onClick={() => setZoom(pxPerSecond * ZOOM_FACTOR)}
      >
        <ZoomIn className='size-4' />
      </Button>

      <Separator orientation='vertical' className='mx-1 h-6' />

      <Button
        size='sm'
        variant='ghost'
        className='h-8 gap-1 text-xs'
        title='Cắt đôi clip tại vạch đỏ (S)'
        disabled={!hasSelection}
        onClick={() =>
          selected && splitClip(selected.trackIndex, selected.clipIndex, currentTime)
        }
      >
        <Scissors className='size-3.5' />
        Cắt đôi
      </Button>
      <Button
        size='icon'
        variant='ghost'
        className='size-8'
        title='Nhân bản clip (Ctrl+D)'
        disabled={!hasSelection}
        onClick={() => selected && duplicateClip(selected.trackIndex, selected.clipIndex)}
      >
        <Copy className='size-4' />
      </Button>
      <Button
        size='icon'
        variant='ghost'
        className='size-8'
        title='Chuyển clip lên trước'
        disabled={!canReorder || selected?.clipIndex === 0}
        onClick={() => selected && moveClip(selected.trackIndex, selected.clipIndex, -1)}
      >
        <ChevronLeft className='size-4' />
      </Button>
      <Button
        size='icon'
        variant='ghost'
        className='size-8'
        title='Chuyển clip ra sau'
        disabled={!canReorder || selected?.clipIndex === (track?.clips.length ?? 0) - 1}
        onClick={() => selected && moveClip(selected.trackIndex, selected.clipIndex, 1)}
      >
        <ChevronRight className='size-4' />
      </Button>
      <Button
        size='icon'
        variant='ghost'
        className='size-8 text-destructive hover:text-destructive'
        title='Xoá clip (Delete)'
        disabled={!hasSelection}
        onClick={() => selected && removeClip(selected.trackIndex, selected.clipIndex)}
      >
        <Trash2 className='size-4' />
      </Button>

      {!hasSelection && (
        <span className='ms-1 text-xs text-muted-foreground'>Chọn 1 clip để thao tác</span>
      )}
    </div>
  )
}
