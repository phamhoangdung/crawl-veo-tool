import { CoverImage } from '@/components/cover-image'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

/**
 * Thumb nhỏ trong bảng, hover thì hiện ảnh to. Thumb ở bảng phải nhỏ để vừa
 * nhiều dòng, nhưng nhỏ quá thì không nhìn được nội dung video — tooltip giải
 * quyết cả hai.
 */
export function ThumbPreview({
  src,
  className,
}: {
  src: string | null
  className?: string
}) {
  // Không có ảnh thì khỏi tooltip: hiện khung rỗng to lên chẳng để làm gì.
  if (!src) {
    return <CoverImage src={null} className={className} />
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type='button' className='block cursor-zoom-in'>
          <CoverImage src={src} className={className} />
        </button>
      </TooltipTrigger>
      <TooltipContent side='right' className='p-1'>
        <CoverImage src={src} className='w-80 rounded' />
      </TooltipContent>
    </Tooltip>
  )
}
