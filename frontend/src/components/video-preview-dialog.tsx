import { ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

/**
 * Popup xem nhanh 1 video qua iframe nhúng chính thức (không tự lấy/giải mã
 * luồng video ở client) — dùng chung cho lưới video Bilibili và YouTube ở
 * trang Trending, trước đây mỗi bên tự viết lại y hệt (chỉ khác URL/nhãn).
 */
export function VideoPreviewDialog({
  title,
  embedUrl,
  externalUrl,
  externalLabel,
  onClose,
}: {
  /** `null` = đóng popup. */
  title: string | null
  embedUrl: string | null
  externalUrl: string | null
  externalLabel: string
  onClose: () => void
}) {
  return (
    <Dialog open={title !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle className='line-clamp-2 pr-6'>{title}</DialogTitle>
        </DialogHeader>
        {embedUrl && externalUrl && (
          <>
            <div className='aspect-video w-full overflow-hidden rounded-md bg-black'>
              <iframe
                src={embedUrl}
                className='h-full w-full'
                allowFullScreen
                title={title ?? ''}
              />
            </div>
            <Button asChild variant='outline' size='sm' className='w-fit'>
              <a href={externalUrl} target='_blank' rel='noopener noreferrer'>
                <ExternalLink className='size-4' />
                {externalLabel}
              </a>
            </Button>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
