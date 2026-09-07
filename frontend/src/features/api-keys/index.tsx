import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pause, Play, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  addApiKey,
  deleteApiKey,
  getApiKeys,
  updateApiKey,
  type ApiKeyRead,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { TaskMonitor } from '@/components/task-monitor'
import { ThemeSwitch } from '@/components/theme-switch'

const PROVIDERS = [
  { id: 'openai', label: 'OpenAI (dịch)' },
  { id: 'elevenlabs', label: 'ElevenLabs (giọng đọc)' },
]

const STATUS_LABEL: Record<ApiKeyRead['status'], string> = {
  active: 'Sẵn sàng',
  cooldown: 'Đang nghỉ (hết quota)',
  exhausted: 'Đã cạn',
  invalid: 'Tạm dừng',
}

const STATUS_VARIANT: Record<
  ApiKeyRead['status'],
  'outline' | 'secondary' | 'destructive'
> = {
  active: 'outline',
  cooldown: 'secondary',
  exhausted: 'destructive',
  invalid: 'destructive',
}

function KeyRow({ apiKey }: { apiKey: ApiKeyRead }) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['api-keys'] })

  const toggleStatus = useMutation({
    mutationFn: () =>
      updateApiKey(apiKey.id, {
        status: apiKey.status === 'invalid' ? 'active' : 'invalid',
      }),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: () => deleteApiKey(apiKey.id),
    onSuccess: () => {
      invalidate()
      toast.success('Đã xoá key.')
    },
  })

  return (
    <div className='flex items-center gap-2 rounded-md border p-2 text-sm'>
      <div className='flex-1 space-y-0.5'>
        <div className='flex items-center gap-2'>
          <span className='font-medium'>{apiKey.label || apiKey.masked_key}</span>
          <Badge variant={STATUS_VARIANT[apiKey.status]} className='text-[10px]'>
            {STATUS_LABEL[apiKey.status]}
          </Badge>
        </div>
        <p className='text-xs text-muted-foreground'>
          {apiKey.masked_key} · {apiKey.request_count} lần dùng
          {apiKey.error_count > 0 && `, ${apiKey.error_count} lỗi`}
          {apiKey.status === 'cooldown' && apiKey.cooldown_until && (
            <> · nghỉ tới {new Date(apiKey.cooldown_until).toLocaleTimeString('vi-VN')}</>
          )}
        </p>
      </div>

      {confirming ? (
        <span className='flex items-center gap-1'>
          <Button
            size='sm'
            variant='destructive'
            className='h-7 text-xs'
            disabled={remove.isPending}
            onClick={() => remove.mutate()}
          >
            Xoá
          </Button>
          <Button
            size='sm'
            variant='ghost'
            className='h-7 text-xs'
            onClick={() => setConfirming(false)}
          >
            Huỷ
          </Button>
        </span>
      ) : (
        <>
          <Button
            size='icon'
            variant='ghost'
            className='size-7'
            title={apiKey.status === 'invalid' ? 'Kích hoạt lại' : 'Tạm dừng key này'}
            disabled={toggleStatus.isPending}
            onClick={() => toggleStatus.mutate()}
          >
            {apiKey.status === 'invalid' ? (
              <Play className='size-3.5' />
            ) : (
              <Pause className='size-3.5' />
            )}
          </Button>
          <Button
            size='icon'
            variant='ghost'
            className='size-7 text-muted-foreground hover:text-destructive'
            title='Xoá key'
            onClick={() => setConfirming(true)}
          >
            <Trash2 className='size-3.5' />
          </Button>
        </>
      )}
    </div>
  )
}

function ProviderKeyPool({ providerId, label }: { providerId: string; label: string }) {
  const [newLabel, setNewLabel] = useState('')
  const [newKey, setNewKey] = useState('')
  const queryClient = useQueryClient()
  const { data: keys } = useQuery({ queryKey: ['api-keys'], queryFn: getApiKeys })
  const providerKeys = keys?.filter((k) => k.provider === providerId) ?? []

  const add = useMutation({
    mutationFn: () => addApiKey(providerId, newKey, newLabel.trim() || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
      setNewKey('')
      setNewLabel('')
      toast.success('Đã thêm key vào pool.')
    },
  })

  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between'>
        <CardTitle className='text-base'>{label}</CardTitle>
        <Badge variant='outline'>{providerKeys.length} key</Badge>
      </CardHeader>
      <CardContent className='space-y-3'>
        {providerKeys.length > 0 && (
          <div className='space-y-2'>
            {providerKeys.map((k) => (
              <KeyRow key={k.id} apiKey={k} />
            ))}
          </div>
        )}

        <form
          className='flex flex-wrap gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            if (newKey.trim()) add.mutate()
          }}
        >
          <Label htmlFor={`${providerId}-label`} className='sr-only'>
            Tên gợi nhớ
          </Label>
          <Input
            id={`${providerId}-label`}
            placeholder='Tên gợi nhớ (tuỳ chọn)'
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            disabled={add.isPending}
            className='w-40'
          />
          <Label htmlFor={`${providerId}-key`} className='sr-only'>
            {label}
          </Label>
          <Input
            id={`${providerId}-key`}
            type='password'
            placeholder='Dán API key để thêm vào pool'
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            disabled={add.isPending}
            className='min-w-48 flex-1'
          />
          <Button type='submit' disabled={add.isPending || !newKey.trim()} className='gap-1'>
            <Plus className='size-3.5' />
            {add.isPending ? 'Đang thêm...' : 'Thêm'}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

export function ApiKeys() {
  return (
    <>
      <Header>
        <Search />
        <div className='ms-auto flex items-center space-x-4'>
          <TaskMonitor />
          <ThemeSwitch />
          <ConfigDrawer />
          <ProfileDropdown />
        </div>
      </Header>

      <Main>
        <div className='mb-4'>
          <h1 className='text-2xl font-bold tracking-tight'>API Keys</h1>
          <p className='text-muted-foreground'>
            Thêm nhiều key cùng 1 nhà cung cấp để tạo pool — khi 1 key hết quota/rate-limit,
            tool tự xoay sang key khác trong pool trước khi chuyển sang provider miễn phí.
          </p>
        </div>

        <div className='flex flex-col gap-4'>
          {PROVIDERS.map((p) => (
            <ProviderKeyPool key={p.id} providerId={p.id} label={p.label} />
          ))}
        </div>
      </Main>
    </>
  )
}
