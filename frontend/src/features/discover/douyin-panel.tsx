import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { getApiErrorMessage, getDouyinStatus, probeDouyinUrl } from '@/lib/api'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

/**
 * Douyin mới làm tới bước thăm dò, chưa tải được video.
 *
 * Nói thẳng điều đó trên giao diện thay vì hiện một ô tìm kiếm trông y hệt
 * Bilibili rồi để người dùng bấm và nhận lỗi khó hiểu. Bước thăm dò không phải
 * làm cho có: nó in ra đúng những trường mà API Douyin trả về, tức là thứ cần
 * biết để viết phần bóc tách link không watermark — mà chỉ cookie thật mới cho biết.
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
