import { memo } from 'react'
import { Handle, Position } from '@xyflow/react'
import { UserRound, X } from 'lucide-react'
import { type CharacterReferenceRead } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { CHARACTER_NODE_WIDTH } from '../graph'

export interface CharacterNodeData extends Record<string, unknown> {
  character: CharacterReferenceRead
  onRemove: (characterId: number) => void
}

function CharacterNodeInner({ data }: { data: CharacterNodeData }) {
  const { character, onRemove } = data

  return (
    <div
      className='bg-card rounded-lg border-2 border-dashed shadow-sm'
      style={{ width: CHARACTER_NODE_WIDTH }}
    >
      <Handle type='source' position={Position.Right} />

      <div className='flex items-center justify-between gap-1 px-2 py-1.5'>
        <span className='flex min-w-0 items-center gap-1 truncate text-sm font-medium'>
          <UserRound className='size-3.5 shrink-0' />
          <span className='truncate'>@{character.name}</span>
        </span>
        <Button
          variant='ghost'
          size='icon'
          className='nodrag size-6 shrink-0'
          title='Bỏ khỏi canvas (không xoá bộ ảnh tham chiếu)'
          onClick={() => onRemove(character.id)}
        >
          <X className='size-3' />
        </Button>
      </div>

      <p className='text-muted-foreground truncate px-2 pb-1.5 text-[10px]'>
        {character.image_count} ảnh
        {character.description ? ` · ${character.description}` : ''}
      </p>

      <p className='text-muted-foreground border-t px-2 py-1 text-[10px]'>
        Kéo cạnh vào 1 cảnh để tự chèn @{character.name} vào prompt.
      </p>
    </div>
  )
}

export const CharacterNode = memo(CharacterNodeInner)
