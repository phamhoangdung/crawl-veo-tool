import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { getPacks, installPack, type PackInfo } from '@/lib/api'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

const PACKS_QUERY_KEY = ['system', 'packs'] as const

const isBusy = (p: PackInfo) =>
  p.state === 'downloading' || p.state === 'extracting'

function progressText(p: PackInfo) {
  if (p.state === 'extracting') return 'Đang giải nén...'
  if (p.total) return `${Math.round((p.downloaded / p.total) * 100)}%`
  return `${Math.round(p.downloaded / 1e6)} MB`
}

/**
 * Shown while a download pack (ffmpeg / AI models) is missing. The installer
 * ships without them to stay small; they are fetched once, on demand.
 */
export function PacksBanner() {
  const queryClient = useQueryClient()
  const { data } = useQuery({
    queryKey: PACKS_QUERY_KEY,
    queryFn: getPacks,
    // Poll fast only while something is downloading.
    refetchInterval: (query) =>
      query.state.data?.some(isBusy) ? 1000 : 30_000,
  })
  const install = useMutation({
    mutationFn: installPack,
    onSuccess: (packs) => queryClient.setQueryData(PACKS_QUERY_KEY, packs),
  })

  const missing = data?.filter((p) => !p.installed) ?? []
  if (missing.length === 0) return null

  return (
    <Alert className='mb-4'>
      <Download className='size-4' />
      <AlertTitle>Cần tải thêm thành phần để dùng đầy đủ tính năng</AlertTitle>
      <AlertDescription>
        <p>
          Bản cài được giữ nhẹ — các thành phần dưới đây tải về 1 lần khi cần.
        </p>
        <ul className='mt-2 space-y-2'>
          {missing.map((p) => (
            <li key={p.id} className='flex flex-wrap items-center gap-3'>
              <span>
                {p.label} (~{p.approx_size_mb} MB)
              </span>
              {isBusy(p) ? (
                <span className='text-muted-foreground'>{progressText(p)}</span>
              ) : (
                <Button
                  size='sm'
                  disabled={install.isPending}
                  onClick={() => install.mutate(p.id)}
                >
                  {p.state === 'error' ? 'Thử lại' : 'Tải về'}
                </Button>
              )}
              {p.state === 'error' && p.error && (
                <span className='text-destructive text-sm'>{p.error}</span>
              )}
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  )
}
