import { useState } from 'react'
import { ScrollText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SystemLogsDialog } from '@/components/system-logs-dialog'

/** Nút mở "Nhật ký hệ thống" trên header — thay cho menu avatar (tạm ẩn). */
export function SystemLogsButton() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button
        variant='ghost'
        size='icon'
        className='size-8 rounded-full'
        title='Nhật ký hệ thống'
        aria-label='Nhật ký hệ thống'
        onClick={() => setOpen(true)}
      >
        <ScrollText className='size-[1.2rem]' />
      </Button>
      <SystemLogsDialog open={open} onOpenChange={setOpen} />
    </>
  )
}
