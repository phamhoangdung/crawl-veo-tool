import { useState } from 'react'
import { type SceneRead } from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'

const MOTIONS = [
  { id: 'zoom_in', label: 'Phóng vào chậm' },
  { id: 'zoom_out', label: 'Thu ra chậm' },
  { id: 'pan_right', label: 'Lia ngang' },
]

const DURATIONS = [3, 4, 5, 8, 10]

export interface ScenePatch {
  duration_seconds?: number
  transition_in?: string
  chain_from_previous?: boolean
  use_ken_burns?: boolean
  ken_burns_motion?: string
}

export function SceneSettingsDialog({
  scene,
  isFirst,
  onSave,
  onOpenChange,
}: {
  scene: SceneRead | null
  isFirst: boolean
  onSave: (sceneId: number, patch: ScenePatch) => void
  onOpenChange: (open: boolean) => void
}) {
  if (!scene) return null

  // `key` buộc remount khi đổi cảnh, nên state khởi tạo thẳng từ props —
  // không cần useEffect đồng bộ (đó là nguồn của cascading render).
  return (
    <SceneSettingsForm
      key={scene.id}
      scene={scene}
      isFirst={isFirst}
      onSave={onSave}
      onOpenChange={onOpenChange}
    />
  )
}

function SceneSettingsForm({
  scene,
  isFirst,
  onSave,
  onOpenChange,
}: {
  scene: SceneRead
  isFirst: boolean
  onSave: (sceneId: number, patch: ScenePatch) => void
  onOpenChange: (open: boolean) => void
}) {
  const [draft, setDraft] = useState<ScenePatch>({
    duration_seconds: scene.duration_seconds,
    transition_in: scene.transition_in,
    chain_from_previous: scene.chain_from_previous,
    use_ken_burns: scene.use_ken_burns,
    ken_burns_motion: scene.ken_burns_motion,
  })

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Tuỳ chọn cảnh {scene.order_index + 1}</DialogTitle>
          <DialogDescription>
            Cảnh không cần chuyển động thật thì để "ảnh tĩnh" — miễn phí và nhanh hơn
            sinh video AI hàng chục lần.
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          <div className='flex items-center justify-between gap-4'>
            <div>
              <Label>Ảnh tĩnh + chuyển động camera</Label>
              <p className='text-muted-foreground text-xs'>
                Tắt để sinh video AI (tốn phí).
              </p>
            </div>
            <Switch
              checked={draft.use_ken_burns ?? true}
              onCheckedChange={(value) => setDraft((d) => ({ ...d, use_ken_burns: value }))}
            />
          </div>

          {draft.use_ken_burns && (
            <div className='space-y-1'>
              <Label htmlFor='motion'>Kiểu chuyển động</Label>
              <Select
                value={draft.ken_burns_motion ?? 'zoom_in'}
                onValueChange={(value) =>
                  setDraft((d) => ({ ...d, ken_burns_motion: value }))
                }
              >
                <SelectTrigger id='motion'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MOTIONS.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className='space-y-1'>
            <Label htmlFor='duration'>Thời lượng</Label>
            <Select
              value={String(draft.duration_seconds ?? 5)}
              onValueChange={(value) =>
                setDraft((d) => ({ ...d, duration_seconds: Number(value) }))
              }
            >
              <SelectTrigger id='duration'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DURATIONS.map((seconds) => (
                  <SelectItem key={seconds} value={String(seconds)}>
                    {seconds}s
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Cảnh đầu không có gì phía trước để nối hay chuyển cảnh từ đó. */}
          {!isFirst && (
            <>
              <div className='space-y-1'>
                <Label htmlFor='transition'>Chuyển cảnh từ cảnh trước</Label>
                <Select
                  value={draft.transition_in ?? 'cut'}
                  onValueChange={(value) =>
                    setDraft((d) => ({ ...d, transition_in: value }))
                  }
                >
                  <SelectTrigger id='transition'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='cut'>Cắt thẳng</SelectItem>
                    <SelectItem value='fade'>Mờ dần (fade)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className='flex items-center justify-between gap-4'>
                <div>
                  <Label>Nối frame từ cảnh trước</Label>
                  <p className='text-muted-foreground text-xs'>
                    Lấy khung cuối cảnh trước làm ảnh mở đầu cảnh này, giữ nhân vật
                    liền mạch.
                  </p>
                </div>
                <Switch
                  checked={draft.chain_from_previous ?? true}
                  onCheckedChange={(value) =>
                    setDraft((d) => ({ ...d, chain_from_previous: value }))
                  }
                />
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button onClick={() => onSave(scene.id, draft)}>Lưu</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
