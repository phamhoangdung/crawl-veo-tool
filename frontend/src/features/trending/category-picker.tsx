import { useMemo, useState } from 'react'
import { type TrendingCategory } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'

/** Chọn chuyên mục muốn theo dõi — gom theo nhóm cho dễ tìm giữa ~39 mục. */
export function CategoryPicker({
  categories,
  selected,
  onChange,
}: {
  categories: TrendingCategory[]
  selected: number[]
  onChange: (rids: number[]) => void
}) {
  const [query, setQuery] = useState('')

  const grouped = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    const matched = keyword
      ? categories.filter(
          (c) =>
            c.name.toLowerCase().includes(keyword) ||
            (c.name_zh ?? '').includes(query.trim())
        )
      : categories

    const map = new Map<string, TrendingCategory[]>()
    for (const category of matched) {
      const group = category.group ?? 'Khác'
      const list = map.get(group)
      if (list) list.push(category)
      else map.set(group, [category])
    }
    return [...map.entries()]
  }, [categories, query])

  function toggle(rid: number) {
    onChange(
      selected.includes(rid)
        ? selected.filter((r) => r !== rid)
        : [...selected, rid]
    )
  }

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant='outline' size='sm'>
          Chọn chuyên mục
          <Badge variant='secondary' className='ms-2'>
            {selected.length}
          </Badge>
        </Button>
      </SheetTrigger>
      <SheetContent className='flex w-full flex-col gap-0 sm:max-w-md'>
        <SheetHeader>
          <SheetTitle>Chuyên mục theo dõi</SheetTitle>
          <SheetDescription>
            Chọn các chuyên mục Bilibili muốn xem ở trang Trending.
          </SheetDescription>
        </SheetHeader>

        <div className='space-y-3 px-4 pb-2'>
          <Input
            placeholder='Tìm chuyên mục...'
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className='flex gap-2'>
            <Button
              size='sm'
              variant='outline'
              onClick={() => onChange(categories.map((c) => c.rid))}
            >
              Chọn tất cả
            </Button>
            <Button size='sm' variant='outline' onClick={() => onChange([])}>
              Bỏ chọn tất cả
            </Button>
          </div>
        </div>

        <div className='flex-1 space-y-4 overflow-y-auto px-4 pb-6'>
          {grouped.map(([group, items]) => (
            <div key={group}>
              <p className='mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase'>
                {group}
              </p>
              <div className='space-y-1'>
                {items.map((category) => (
                  <label
                    key={category.rid}
                    className='flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-accent'
                  >
                    <Checkbox
                      checked={selected.includes(category.rid)}
                      onCheckedChange={() => toggle(category.rid)}
                    />
                    <span className='flex-1'>{category.name}</span>
                    <span className='text-xs text-muted-foreground'>
                      {category.name_zh}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          ))}
          {grouped.length === 0 && (
            <p className='text-sm text-muted-foreground'>
              Không tìm thấy chuyên mục nào khớp.
            </p>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
