import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { Check, Copy, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  createMcpToken,
  getMcpScopes,
  getMcpTokens,
  revokeMcpToken,
  type McpTokenCreated,
  type McpTokenRead,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

/** Scope mặc định tick sẵn — đủ để agent chạy trọn luồng sinh ảnh/video. */
const DEFAULT_SCOPES = ['assets:read', 'assets:write', 'gen:write', 'jobs:read', 'cost:read']

const SCOPE_HINT: Record<string, string> = {
  'assets:read': 'xem bộ ảnh tham chiếu',
  'assets:write': 'tạo/xoá bộ ảnh tham chiếu',
  'gen:write': 'sinh ảnh/video (tốn phí)',
  'jobs:read': 'xem kết quả đã sinh',
  'cost:read': 'xem chi phí & hạn mức',
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false)

  return (
    <Button
      variant='outline'
      size='sm'
      className='gap-1'
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value)
          setCopied(true)
          setTimeout(() => setCopied(false), 2000)
        } catch {
          toast.error('Không copy được — chọn thủ công rồi Ctrl+C.')
        }
      }}
    >
      {copied ? <Check className='size-3.5' /> : <Copy className='size-3.5' />}
      {copied ? 'Đã copy' : label}
    </Button>
  )
}

function CreatedTokenPanel({ created }: { created: McpTokenCreated }) {
  const configJson = JSON.stringify(created.mcp_config, null, 2)

  return (
    <div className='border-destructive/50 bg-destructive/5 space-y-3 rounded-md border p-3'>
      <p className='text-sm font-medium'>{created.warning}</p>

      <div className='space-y-1'>
        <Label className='text-xs'>Token</Label>
        <div className='flex items-center gap-2'>
          <code className='bg-muted min-w-0 flex-1 truncate rounded px-2 py-1.5 font-mono text-xs'>
            {created.plain_token}
          </code>
          <CopyButton value={created.plain_token} label='Copy' />
        </div>
      </div>

      <div className='space-y-1'>
        <div className='flex items-center justify-between gap-2'>
          <Label className='text-xs'>Config MCP (dán vào Claude Code / Codex)</Label>
          <CopyButton value={configJson} label='Copy config' />
        </div>
        <pre className='bg-muted max-h-56 overflow-auto rounded p-2 font-mono text-xs'>
          {configJson}
        </pre>
      </div>
    </div>
  )
}

function TokenRow({ token }: { token: McpTokenRead }) {
  const queryClient = useQueryClient()
  const revoked = token.revoked_at != null

  const revoke = useMutation({
    mutationFn: () => revokeMcpToken(token.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcp-tokens'] })
      toast.success(`Đã thu hồi token "${token.name}".`)
    },
    onError: () => toast.error('Không thu hồi được token.'),
  })

  return (
    <div className='flex items-center gap-2 rounded-md border p-2 text-sm'>
      <div className='min-w-0 flex-1'>
        <div className='flex items-center gap-2'>
          <span className='font-medium'>{token.name}</span>
          {revoked && <Badge variant='destructive'>Đã thu hồi</Badge>}
        </div>
        <p className='text-muted-foreground truncate text-xs'>
          {token.scopes.length} scope · tạo{' '}
          {new Date(token.created_at).toLocaleDateString('vi-VN')}
          {token.last_used_at
            ? ` · dùng lần cuối ${new Date(token.last_used_at).toLocaleString('vi-VN')}`
            : ' · chưa dùng'}
        </p>
      </div>
      {!revoked && (
        <Button
          variant='ghost'
          size='icon'
          className='text-muted-foreground hover:text-destructive size-7'
          title='Thu hồi token'
          onClick={() => revoke.mutate()}
          disabled={revoke.isPending}
        >
          <Trash2 className='size-3.5' />
        </Button>
      )}
    </div>
  )
}

export function McpTokenSection() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('claude-code')
  const [selectedScopes, setSelectedScopes] = useState<string[]>(DEFAULT_SCOPES)
  const [created, setCreated] = useState<McpTokenCreated | null>(null)

  const scopes = useQuery({ queryKey: ['mcp-scopes'], queryFn: getMcpScopes })
  const tokens = useQuery({ queryKey: ['mcp-tokens'], queryFn: getMcpTokens })

  const create = useMutation({
    mutationFn: () => createMcpToken(name.trim(), selectedScopes),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['mcp-tokens'] })
      setCreated(result)
      toast.success('Đã tạo token — copy ngay, sẽ không hiện lại.')
    },
    onError: (error) => {
      const detail = axios.isAxiosError(error)
        ? (error.response?.data as { detail?: string })?.detail
        : null
      toast.error(detail ?? 'Không tạo được token.')
    },
  })

  const toggleScope = (scope: string) =>
    setSelectedScopes((current) =>
      current.includes(scope) ? current.filter((s) => s !== scope) : [...current, scope]
    )

  const canCreate = name.trim().length > 0 && selectedScopes.length > 0

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>
          MCP Access Token (cho agent ngoài: Claude Code, Codex)
        </CardTitle>
      </CardHeader>
      <CardContent className='space-y-3'>
        <p className='text-muted-foreground text-sm'>
          Token cho agent tự vận hành AI Studio (sinh ảnh, sinh clip) mà không cần bạn thao
          tác qua giao diện. Scope hẹp có chủ đích: agent không đụng được vào API key của
          nhà cung cấp hay cấu hình hệ thống.
        </p>

        {tokens.data && tokens.data.length > 0 && (
          <div className='space-y-2'>
            {tokens.data.map((token) => (
              <TokenRow key={token.id} token={token} />
            ))}
          </div>
        )}

        {created && <CreatedTokenPanel created={created} />}

        <div className='space-y-2 rounded-md border p-3'>
          <div className='space-y-1'>
            <Label htmlFor='mcp-token-name'>Tên token</Label>
            <Input
              id='mcp-token-name'
              placeholder='vd claude-code'
              value={name}
              onChange={(e) => setName(e.target.value)}
              className='max-w-64'
            />
          </div>

          <div className='space-y-1'>
            <Label>Quyền được cấp</Label>
            <div className='grid gap-1.5 sm:grid-cols-2'>
              {(scopes.data ?? DEFAULT_SCOPES).map((scope) => (
                <label key={scope} className='flex items-center gap-2 text-sm'>
                  <Checkbox
                    checked={selectedScopes.includes(scope)}
                    onCheckedChange={() => toggleScope(scope)}
                  />
                  <code className='text-xs'>{scope}</code>
                  {SCOPE_HINT[scope] && (
                    <span className='text-muted-foreground text-xs'>
                      — {SCOPE_HINT[scope]}
                    </span>
                  )}
                </label>
              ))}
            </div>
          </div>

          <Button
            onClick={() => create.mutate()}
            disabled={!canCreate || create.isPending}
            className='gap-1'
          >
            <Plus className='size-3.5' />
            {create.isPending ? 'Đang tạo...' : 'Tạo token'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
