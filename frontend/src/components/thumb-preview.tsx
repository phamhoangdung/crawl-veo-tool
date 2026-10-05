import { CoverImage } from '@/components/cover-image'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

/**
 * A small thumb in a table, showing a large image on hover. A thumb in a table must be small to fit
 * many rows, but too small and the video content cannot be seen — the tooltip solves
 * both.
 */
export function ThumbPreview({
  src,
  className,
}: {
  src: string | null
  className?: string
}) {
  // No image means no tooltip: showing a big empty frame serves no purpose.
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
