import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getApiKeys, saveApiKey } from '@/lib/api'
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
import { ThemeSwitch } from '@/components/theme-switch'

const PROVIDERS = [
  { id: 'openai', label: 'OpenAI (dịch)' },
  { id: 'elevenlabs', label: 'ElevenLabs (giọng đọc)' },
]

function ProviderKeyForm({ providerId, label }: { providerId: string; label: string }) {
  const [value, setValue] = useState('')
  const queryClient = useQueryClient()
  const { data: keys } = useQuery({ queryKey: ['api-keys'], queryFn: getApiKeys })
  const existing = keys?.find((k) => k.provider === providerId)

  const mutation = useMutation({
    mutationFn: () => saveApiKey(providerId, value),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
      setValue('')
    },
  })

  return (
    <Card>
      <CardHeader className='flex flex-row items-center justify-between'>
        <CardTitle className='text-base'>{label}</CardTitle>
        {existing && <Badge variant='outline'>Đã lưu: {existing.masked_key}</Badge>}
      </CardHeader>
      <CardContent>
        <form
          className='flex gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            if (value.trim()) mutation.mutate()
          }}
        >
          <Label htmlFor={providerId} className='sr-only'>
            {label}
          </Label>
          <Input
            id={providerId}
            type='password'
            placeholder={existing ? 'Nhập key mới để thay thế' : 'Dán API key vào đây'}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            disabled={mutation.isPending}
          />
          <Button type='submit' disabled={mutation.isPending || !value.trim()}>
            {mutation.isPending ? 'Đang lưu...' : 'Lưu'}
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
          <ThemeSwitch />
          <ConfigDrawer />
          <ProfileDropdown />
        </div>
      </Header>

      <Main>
        <div className='mb-4'>
          <h1 className='text-2xl font-bold tracking-tight'>API Keys</h1>
          <p className='text-muted-foreground'>
            Nếu đã cấu hình và key hoạt động, tool ưu tiên dùng provider trả phí; nếu không sẽ tự
            dùng provider miễn phí (Google Translate, Edge-TTS).
          </p>
        </div>

        <div className='flex flex-col gap-4'>
          {PROVIDERS.map((p) => (
            <ProviderKeyForm key={p.id} providerId={p.id} label={p.label} />
          ))}
        </div>
      </Main>
    </>
  )
}
