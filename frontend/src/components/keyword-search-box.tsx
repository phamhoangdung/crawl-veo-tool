import type { FormEvent } from 'react'
import { Search as SearchIcon, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

/**
 * Ô tìm kiếm theo từ khoá dùng chung cho trang Crawl và Trending — cả 2 đều
 * search trên Bilibili, vốn chỉ ra kết quả tốt với từ khoá tiếng Trung. Trước
 * đây mỗi trang tự viết JSX riêng nên tuỳ chọn "dịch sang tiếng Trung" chỉ có
 * ở trang Crawl mà thiếu hẳn ở Trending — component chung này đảm bảo thêm
 * tính năng tìm kiếm ở đâu cũng có sẵn tuỳ chọn dịch, không lệch nhau nữa.
 */
export interface KeywordSearchBoxProps {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  placeholder: string
  /** Mặc định 'Tìm'. */
  submitLabel?: string
  pendingLabel?: string
  isPending?: boolean
  translateKeyword: boolean
  onTranslateKeywordChange: (value: boolean) => void
  /** Hiện nút xoá tìm kiếm (Trending dùng để quay lại danh sách mặc định). */
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
