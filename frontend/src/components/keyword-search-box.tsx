import type { FormEvent } from 'react'
import { Search as SearchIcon, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

/**
 * A keyword search box shared by the Crawl and Trending pages — both
 * search on Bilibili, which only gives good results with Chinese keywords. Previously
 * each page wrote its own JSX so the "translate to Chinese" option only existed
 * on the Crawl page and was missing entirely from Trending — this shared component ensures that wherever a
 * search feature is added, the translate option is there too, no longer drifting apart.
 */
export interface KeywordSearchBoxProps {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  placeholder: string
  /** Defaults to 'Tìm'. */
  submitLabel?: string
  pendingLabel?: string
  isPending?: boolean
  translateKeyword: boolean
  onTranslateKeywordChange: (value: boolean) => void
  /** Show the clear-search button (Trending uses it to return to the default list). */
  onClear?: () => void
  className?: string
  inputClassName?: string
}

export function KeywordSearchBox({
  value,
  onChange,
  onSubmit,
  placeholder,
  submitLabel = 'Tìm',
  pendingLabel = 'Đang tìm...',
  isPending = false,
  translateKeyword,
  onTranslateKeywordChange,
  onClear,
  className,
  inputClassName,
}: KeywordSearchBoxProps) {
  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (value.trim()) onSubmit()
  }

  return (
    <form className={cn('space-y-3', className)} onSubmit={handleSubmit}>
      <div className='flex gap-2'>
        <Input
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={isPending}
          className={inputClassName}
        />
        <Button type='submit' variant='secondary' disabled={isPending || !value.trim()}>
          <SearchIcon className='size-4' />
          {isPending ? pendingLabel : submitLabel}
        </Button>
        {onClear && (
          <Button type='button' variant='ghost' onClick={onClear}>
            <X className='size-4' />
            Xoá tìm kiếm
          </Button>
        )}
      </div>
      <label className='flex items-center gap-2 text-sm text-muted-foreground'>
        <Checkbox
          checked={translateKeyword}
          onCheckedChange={(checked) => onTranslateKeywordChange(checked === true)}
          disabled={isPending}
        />
        Dịch từ khoá sang tiếng Trung giản thể trước khi tìm
      </label>
    </form>
  )
}
