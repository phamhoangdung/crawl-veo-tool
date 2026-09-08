import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ImageIcon, Music, Trash2, Upload, Video as VideoIcon } from 'lucide-react'
import { toast } from 'sonner'
import {
  type Asset,
  type AssetKind,
  assetFileUrl,
  deleteAsset,
  listAssets,
  uploadAsset,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const KIND_ICON = {
  image: ImageIcon,
  video: VideoIcon,
  audio: Music,
} as const

const KIND_HINT: Record<AssetKind, string> = {
  image: 'PNG, JPG, WEBP — nền trong suốt (PNG) cho logo đẹp nhất',
  video: 'MP4, MOV, MKV, WEBM',
  audio: 'MP3, WAV, M4A, AAC, FLAC',
}

function formatSize(bytes: number) {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

/**
 * Chọn file từ kho dùng chung (logo, intro/outro, nhạc nền). Lọc theo `kind` vì
 * mỗi chỗ gọi chỉ nhận đúng một loại — chọn nhầm .mp3 làm logo thì ffmpeg mới
 * báo lỗi, quá muộn.
 */
export function AssetPicker({
  open,
  kind,
  title,
  description,
  onSelect,
  onOpenChange,
}: {
  open: boolean
  kind: AssetKind
  title: string
  description: string
  onSelect: (asset: Asset) => void
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const { data: assets = [], isLoading } = useQuery({
    queryKey: ['assets', kind],
    queryFn: () => listAssets(kind),
    enabled: open,
  })

  const upload = useMutation({
    mutationFn: uploadAsset,
    onSuccess: (asset) => {
      queryClient.invalidateQueries({ queryKey: ['assets'] })
      if (asset.kind !== kind) {
        // Vẫn lưu vào kho (không vứt file người dùng đã tải lên), nhưng nói rõ
        // vì sao nó không hiện trong danh sách đang mở.
        toast.warning(`Đã lưu "${asset.name}" vào kho ${asset.kind}, không phải ${kind}`)
        return
      }
      toast.success(`Đã tải lên "${asset.name}"`)
      onSelect(asset)
      onOpenChange(false)
    },
    onError: (error: unknown) => {
      const detail =
        (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
      toast.error(detail ?? 'Tải file lên thất bại')
    },
  })

  const remove = useMutation({
    mutationFn: deleteAsset,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['assets'] }),
    onError: () => toast.error('Không xoá được file'),
  })

  const Icon = KIND_ICON[kind]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            const file = e.dataTransfer.files[0]
            if (file) upload.mutate(file)
          }}
          className={cn(
            'rounded-lg border-2 border-dashed p-4 text-center transition-colors',
            dragging ? 'border-primary bg-primary/5' : 'border-muted'
          )}
        >
          <Icon className='mx-auto mb-2 size-6 text-muted-foreground' />
          <p className='text-sm'>Kéo thả file vào đây, hoặc</p>
          <Button
            type='button'
            size='sm'
            variant='outline'
            className='mt-2 gap-1'
            disabled={upload.isPending}
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload className='size-3.5' />
            {upload.isPending ? 'Đang tải lên…' : 'Chọn file'}
          </Button>
          <p className='mt-2 text-xs text-muted-foreground'>{KIND_HINT[kind]}</p>
          <input
            ref={fileInputRef}
            type='file'
            className='hidden'
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) upload.mutate(file)
              // Reset để chọn lại đúng file vừa xoá vẫn kích hoạt onChange.
              e.target.value = ''
            }}
          />
        </div>

        <div className='max-h-64 space-y-1 overflow-y-auto'>
          {isLoading && <p className='text-sm text-muted-foreground'>Đang tải…</p>}
          {!isLoading && assets.length === 0 && (
            <p className='py-4 text-center text-sm text-muted-foreground'>
              Kho chưa có file nào. Tải lên file đầu tiên ở trên.
            </p>
          )}
          {assets.map((asset) => (
            <div
              key={asset.id}
              className='flex items-center gap-2 rounded border p-2 hover:bg-accent'
            >
              <button
                type='button'
                className='flex min-w-0 flex-1 items-center gap-2 text-start'
                onClick={() => {
                  onSelect(asset)
                  onOpenChange(false)
                }}
              >
                {asset.kind === 'image' ? (
                  <img
                    src={assetFileUrl(asset.id)}
                    alt=''
                    className='size-9 shrink-0 rounded border bg-muted object-contain'
                  />
                ) : (
                  <span className='flex size-9 shrink-0 items-center justify-center rounded border bg-muted'>
                    <Icon className='size-4 text-muted-foreground' />
                  </span>
                )}
                <span className='min-w-0'>
                  <span className='block truncate text-sm'>{asset.name}</span>
                  <span className='block text-xs text-muted-foreground'>
                    {formatSize(asset.size)}
                  </span>
                </span>
              </button>
              <Button
                type='button'
                size='icon'
                variant='ghost'
                className='size-7 shrink-0'
                aria-label={`Xoá ${asset.name}`}
                onClick={() => remove.mutate(asset.id)}
              >
                <Trash2 className='size-3.5' />
              </Button>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
