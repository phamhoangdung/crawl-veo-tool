import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  createCharacterReference,
  deleteCharacterReference,
  getCharacterReferences,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

const SLUG_PATTERN = /^[a-z0-9_]+$/

function CreateReferenceDialog() {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [files, setFiles] = useState<File[]>([])

  const normalised = name.trim().toLowerCase()
  const slugError =
    normalised.length > 0 && !SLUG_PATTERN.test(normalised)
      ? 'Chỉ dùng chữ thường không dấu, số và _ (vì tên này được gọi trong prompt dạng @ten).'
      : null

  const reset = () => {
    setName('')
    setDescription('')
    setFiles([])
  }

  const create = useMutation({
    mutationFn: () => createCharacterReference(normalised, files, description || undefined),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['ai-studio', 'character-references'] })
      toast.success(`Đã tạo bộ ảnh @${created.name}.`)
      setOpen(false)
      reset()
    },
    onError: (error) => {
      const detail = axios.isAxiosError(error)
        ? (error.response?.data as { detail?: string })?.detail
        : null
      toast.error(detail ?? 'Không tạo được bộ ảnh tham chiếu.')
    },
  })

  const canSubmit = normalised.length > 0 && !slugError && files.length > 0

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) reset()
      }}
    >
      <DialogTrigger asChild>
        <Button variant='outline' size='sm' className='w-full gap-1'>
          <Plus className='size-3.5' />
          Thêm bộ ảnh
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Thêm bộ ảnh tham chiếu</DialogTitle>
          <DialogDescription>
            Ảnh tham chiếu được đính kèm vào mọi lần sinh để nhân vật giữ đặc điểm xuyên
            nhiều cảnh. Nên có 2-4 góc (trước, nghiêng, cận mặt).
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-3'>
          <div className='space-y-1'>
            <Label htmlFor='ref-name'>Tên gọi trong prompt</Label>
            <Input
              id='ref-name'
              placeholder='vd sunhui_hero'
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            {slugError ? (
              <p className='text-destructive text-xs'>{slugError}</p>
            ) : (
              <p className='text-muted-foreground text-xs'>
                Sẽ gọi trong prompt là{' '}
                <code>@{normalised || 'ten_ban_dat'}</code>
              </p>
            )}
          </div>

          <div className='space-y-1'>
            <Label htmlFor='ref-desc'>Mô tả (tuỳ chọn)</Label>
            <Textarea
              id='ref-desc'
              placeholder='vd bà cụ tóc bạc, áo len xanh'
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>

          <div className='space-y-1'>
            <Label htmlFor='ref-images'>Ảnh nhân vật</Label>
            <Input
              id='ref-images'
              type='file'
              accept='image/png,image/jpeg,image/webp'
              multiple
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            />
            {files.length > 0 && files.length < 2 && (
              <p className='text-muted-foreground text-xs'>
                Chỉ có 1 ảnh — nên thêm 2-4 góc để nhân vật nhất quán hơn giữa các cảnh.
              </p>
            )}
            {files.length >= 2 && (
              <p className='text-muted-foreground text-xs'>Đã chọn {files.length} ảnh.</p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={() => create.mutate()}
            disabled={!canSubmit || create.isPending}
          >
            {create.isPending ? 'Đang tạo...' : 'Tạo bộ ảnh'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function CharacterReferencePanel() {
  const queryClient = useQueryClient()
  const references = useQuery({
    queryKey: ['ai-studio', 'character-references'],
    queryFn: getCharacterReferences,
  })

  const remove = useMutation({
    mutationFn: deleteCharacterReference,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ai-studio', 'character-references'] })
      toast.success('Đã xoá bộ ảnh tham chiếu.')
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>Bộ ảnh tham chiếu</CardTitle>
      </CardHeader>
      <CardContent className='space-y-2'>
        {references.isLoading && (
          <p className='text-muted-foreground text-sm'>Đang tải...</p>
        )}

        {references.data?.length === 0 && (
          <p className='text-muted-foreground text-sm'>
            Chưa có bộ ảnh nào. Tạo một bộ để nhân vật giữ đặc điểm giống nhau giữa các cảnh.
          </p>
        )}

        {references.data?.map((reference) => (
          <div
            key={reference.id}
            className='flex items-center gap-2 rounded-md border p-2 text-sm'
          >
            <div className='min-w-0 flex-1'>
              <code className='font-medium'>@{reference.name}</code>
              <p className='text-muted-foreground truncate text-xs'>
                {reference.image_count} ảnh
                {reference.description ? ` · ${reference.description}` : ''}
              </p>
            </div>
            <Button
              variant='ghost'
              size='icon'
              className='size-7'
              onClick={() => remove.mutate(reference.id)}
              disabled={remove.isPending}
              aria-label={`Xoá bộ ảnh ${reference.name}`}
            >
              <Trash2 className='size-3.5' />
            </Button>
          </div>
        ))}

        <CreateReferenceDialog />
      </CardContent>
    </Card>
  )
}
