import { useState } from 'react'
import { ScrollText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SystemLogsDialog } from '@/components/system-logs-dialog'

/** Button that opens the "Nhật ký hệ thống" (System log) on the header — replaces the avatar menu (temporarily hidden). */
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
