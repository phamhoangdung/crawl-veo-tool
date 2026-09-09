import { useMutation, useQuery } from '@tanstack/react-query'
import axios from 'axios'
import { toast } from 'sonner'
import {
  exportGeneratedAssetToLibrary,
  generatedAssetFileUrl,
  getGeneratedAssets,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

function ExportButton({ assetId }: { assetId: number }) {
  const exportToLibrary = useMutation({
    mutationFn: () => exportGeneratedAssetToLibrary(assetId),
    onSuccess: (result) => {
      toast.success(
        `Đã thêm "${result.name}" vào kho dùng chung — chọn được trong Timeline Editor.`
      )
    },
    onError: (error) => {
      const detail = axios.isAxiosError(error)
        ? (error.response?.data as { detail?: string })?.detail
        : null
      toast.error(detail ?? 'Không thêm được vào kho.')
    },
  })

  return (
    <Button
      variant='ghost'
      size='sm'
      onClick={() => exportToLibrary.mutate()}
      disabled={exportToLibrary.isPending}
    >
      {exportToLibrary.isPending ? 'Đang thêm...' : 'Vào kho'}
    </Button>
  )
}

export function SessionHistory() {
  const assets = useQuery({
    queryKey: ['ai-studio', 'assets'],
    queryFn: () => getGeneratedAssets(),
  })

  const rows = assets.data ?? []
  const totalCost = rows.reduce((sum, asset) => sum + asset.cost_estimate_usd, 0)
  const freeCount = rows.filter((asset) => asset.cost_estimate_usd === 0).length

  if (rows.length === 0) return null

  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between'>
        <CardTitle className='text-base'>Đã tạo ({rows.length})</CardTitle>
        <Badge variant='outline'>
          Tổng: ${totalCost.toFixed(2)}
          {freeCount > 0 ? ` · ${freeCount} miễn phí` : ''}
        </Badge>
      </CardHeader>
      <CardContent className='space-y-2'>
        {rows.slice(0, 12).map((asset) => (
          <div
            key={asset.id}
            className='flex items-center gap-2 rounded-md border p-2 text-sm'
          >
            <Badge variant='secondary' className='shrink-0'>
              {asset.type === 'image' ? 'Ảnh' : 'Clip'}
            </Badge>
            <div className='min-w-0 flex-1'>
              <p className='truncate'>{asset.prompt}</p>
              <p className='text-muted-foreground text-xs'>
                #{asset.id} · {asset.model}
                {asset.duration_seconds ? ` · ${asset.duration_seconds}s` : ''} ·{' '}
                {asset.cost_estimate_usd === 0
                  ? 'miễn phí'
                  : `$${asset.cost_estimate_usd.toFixed(3)}`}
              </p>
            </div>
            <ExportButton assetId={asset.id} />
            <Button variant='ghost' size='sm' asChild>
              <a
                href={generatedAssetFileUrl(asset.id)}
                target='_blank'
                rel='noreferrer'
              >
                Mở
              </a>
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
