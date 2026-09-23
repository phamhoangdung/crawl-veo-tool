import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Copy, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { getSystemLogs } from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

type Props = { open: boolean; onOpenChange: (open: boolean) => void }

/** Xem nhật ký backend ngay trong app — bản đóng gói không còn cửa sổ console. */
export function SystemLogsDialog({ open, onOpenChange }: Props) {
  const [autoRefresh, setAutoRefresh] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  const { data, isFetching, isError, refetch } = useQuery({
    queryKey: ['system', 'logs'],
    queryFn: () => getSystemLogs(500),
    enabled: open,
    refetchInterval: open && autoRefresh ? 2000 : false,
  })

  const text = data?.lines.join('\n') ?? ''

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [open, text])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      toast.success('Đã sao chép nhật ký.')
    } catch {
      toast.error('Không sao chép được nhật ký.')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>Nhật ký hệ thống</DialogTitle>
          <DialogDescription className='break-all'>
            {data?.path ?? 'Nhật ký hoạt động của dịch vụ nền (backend).'}
          </DialogDescription>
        </DialogHeader>

        <div className='flex flex-wrap items-center justify-between gap-2'>
          <div className='flex items-center gap-2'>
            <Switch
              id='logs-auto-refresh'
              checked={autoRefresh}
              onCheckedChange={setAutoRefresh}
            />
            <Label htmlFor='logs-auto-refresh'>Tự động cập nhật</Label>
          </div>
          <div className='flex gap-2'>
            <Button
              variant='outline'
              size='sm'
              onClick={() => refetch()}
              disabled={isFetching}
            >
              <RefreshCw
                className={isFetching ? 'size-3.5 animate-spin' : 'size-3.5'}
              />
              Làm mới
            </Button>
            <Button variant='outline' size='sm' onClick={copy} disabled={!text}>
              <Copy className='size-3.5' />
              Sao chép
            </Button>
          </div>
        </div>

        <div className='h-[55vh] overflow-auto rounded-md border bg-muted/40 p-3'>
          {isError ? (
            <p className='text-sm text-destructive'>
              Không đọc được nhật ký — backend chưa sẵn sàng.
            </p>
          ) : data && !data.exists ? (
            <p className='text-sm text-muted-foreground'>
              Chưa có nhật ký nào.
            </p>
          ) : (
            <pre className='font-mono text-xs leading-relaxed break-all whitespace-pre-wrap'>
              {text}
            </pre>
          )}
          <div ref={bottomRef} />
        </div>
      </DialogContent>
    </Dialog>
  )
}
