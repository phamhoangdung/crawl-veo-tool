import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Languages } from 'lucide-react'
import { translateText } from '@/lib/api'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

/** Có ký tự Hán nào không — không có thì khỏi dịch, đỡ tốn quota. */
function hasChinese(text: string) {
  return /[一-鿿]/.test(text)
}

/**
 * Tiêu đề tiếng Trung, hover thì hiện bản dịch tiếng Việt.
 *
 * Dịch theo kiểu lười (chỉ khi hover) chứ không dịch sẵn cả danh sách: mở trang
 * là dịch 40 tiêu đề thì đốt quota cho những dòng người dùng không bao giờ xem.
 * Kết quả được cache 2 tầng — TanStack Query trong phiên, và DB ở backend nên
 * còn nguyên sau khi restart.
 */
export function TranslatedTitle({
  title,
  href,
  className,
}: {
  title: string
  href?: string
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const shouldTranslate = hasChinese(title)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['translate', title],
    queryFn: () => translateText(title),
    // Chỉ gọi khi tooltip đã mở thật.
    enabled: open && shouldTranslate,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: false,
  })

  // Tiêu đề không có chữ Hán thì giữ hành vi cũ: title= của trình duyệt.
  if (!shouldTranslate) {
    return href ? (
      <a href={href} target='_blank' rel='noreferrer' className={className} title={title}>
        {title}
      </a>
    ) : (
      <span className={className} title={title}>
        {title}
      </span>
    )
  }

  return (
    <Tooltip open={open} onOpenChange={setOpen}>
      <TooltipTrigger asChild>
        {href ? (
          <a href={href} target='_blank' rel='noreferrer' className={className}>
            {title}
          </a>
        ) : (
          <span className={className}>{title}</span>
        )}
      </TooltipTrigger>
      <TooltipContent side='top' className='max-w-md'>
        {/* Hiện cả nguyên văn: bản dịch máy có thể sai, người dùng cần đối chiếu. */}
        <p className='mb-1 text-[11px] opacity-70'>{title}</p>
        {isLoading && <p className='flex items-center gap-1'>Đang dịch…</p>}
        {isError && <p>Không dịch được (kiểm tra API key hoặc quota)</p>}
        {data && (
          <p className='flex items-start gap-1 font-medium'>
            <Languages className='mt-0.5 size-3 shrink-0' />
            {data.translated_text}
          </p>
        )}
      </TooltipContent>
    </Tooltip>
  )
}
