import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { getApiErrorMessage, getDouyinStatus, probeDouyinUrl } from '@/lib/api'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

/**
 * Douyin has only reached the probing step, videos cannot be downloaded yet.
 *
 * Say so plainly on the UI instead of showing a search box that looks identical to
 * Bilibili's and letting the user click and get a confusing error. The probing step is not
 * just for show: it prints exactly the fields the Douyin API returns, which is what is needed to
 * know to write the no-watermark link extraction — and only a real cookie can reveal it.
 */
export function DouyinPanel() {
  const [shareUrl, setShareUrl] = useState('')

  const status = useQuery({
    queryKey: ['douyin', 'status'],
    queryFn: getDouyinStatus,
  })

  const probe = useMutation({
    mutationFn: () => probeDouyinUrl(shareUrl.trim()),
  })

  const configured = status.data?.configured ?? false

  const errorMessage = probe.isError
    ? getApiErrorMessage(probe.error, 'Thăm dò thất bại.')
    : null

  return (
    <div className='space-y-3'>
      {!configured && (
        <Alert>
          <AlertTitle>Chưa cấu hình cookie Douyin</AlertTitle>
          <AlertDescription>
            <span>
              Đăng nhập Douyin trên trình duyệt, mở DevTools → Network → copy
              header <code className='font-mono'>Cookie</code>, dán vào{' '}
              <code className='font-mono'>DOUYIN_COOKIE</code> trong{' '}
              <code className='font-mono'>backend/.env</code> rồi khởi động lại
              backend.
            </span>
          </AlertDescription>
        </Alert>
      )}

      <Alert>
        <AlertTitle>Douyin mới hỗ trợ một phần</AlertTitle>
        <AlertDescription>
          <span>
            Hiện chỉ thăm dò được link chia sẻ (lấy id + xem API trả về những
            trường gì). Chưa tải được video: cấu trúc dữ liệu của Douyin không có
            tài liệu công khai, cần chạy thăm dò bằng cookie thật một lần rồi mới
            viết phần tải được cho đúng.
          </span>
        </AlertDescription>
      </Alert>

      <form
        className='flex gap-2'
        onSubmit={(e) => {
          e.preventDefault()
          if (shareUrl.trim()) probe.mutate()
        }}
      >
        <Input
          placeholder='Dán link chia sẻ, vd: https://v.douyin.com/xxxxxxx/'
          value={shareUrl}
          onChange={(e) => setShareUrl(e.target.value)}
          disabled={probe.isPending}
        />
        <Button type='submit' disabled={probe.isPending || !shareUrl.trim()}>
          {probe.isPending ? 'Đang thăm dò...' : 'Thăm dò'}
        </Button>
      </form>

      {errorMessage && (
        <p className='text-destructive text-sm'>{errorMessage}</p>
      )}

      {probe.data && (
        <div className='space-y-1 rounded-md border p-3 text-xs'>
          <p>
            <span className='text-muted-foreground'>aweme_id:</span>{' '}
            <code className='font-mono'>{probe.data.aweme_id}</code>
          </p>
          <p>
            <span className='text-muted-foreground'>Trường ở tầng ngoài:</span>{' '}
            <code className='font-mono'>
              {probe.data.top_level_keys.join(', ') || '(rỗng)'}
            </code>
          </p>
          <p>
            <span className='text-muted-foreground'>Trường trong detail:</span>{' '}
            <code className='font-mono'>
              {probe.data.detail_keys.join(', ') || '(rỗng)'}
            </code>
          </p>
          <p className='text-muted-foreground pt-1'>
            Gửi danh sách trường này cho phiên làm việc sau để viết phần tải video
            không watermark.
          </p>
        </div>
      )}
    </div>
  )
}
