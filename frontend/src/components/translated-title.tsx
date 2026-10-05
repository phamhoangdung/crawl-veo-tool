import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Languages } from 'lucide-react'
import { translateText } from '@/lib/api'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

/** Whether there is any Han character — if none, skip translating, saving quota. */
function hasChinese(text: string) {
  return /[一-鿿]/.test(text)
}

/**
 * A Chinese title, showing the Vietnamese translation on hover.
 *
 * Translated lazily (only on hover) rather than pre-translating the whole list: opening the page
 * would translate 40 titles and burn quota on rows the user never looks at.
 * The result is cached in 2 layers — TanStack Query within the session, and the DB in the backend so it
 * survives a restart.
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
    // Only call once the tooltip has really opened.
    enabled: open && shouldTranslate,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: false,
  })

  // A title without Han characters keeps the old behavior: the browser's title=.
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
        {/* Show the original too: machine translation can be wrong, the user needs to cross-check. */}
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
