import { useState } from 'react'
import { Film, ImageIcon, Music } from 'lucide-react'
import { toast } from 'sonner'
import type { Asset, AssetKind, TimelineTrack } from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { AssetPicker } from './asset-picker'
import { useEditorStore } from './store'

/** Default duration for intro/outro when the real length of the file cannot be read.
 * The user adjusts it in the "Clip details" panel — this is only a starting point. */
const DEFAULT_CLIP_SECONDS = 5

type Slot = 'intro' | 'outro' | 'logo' | 'music'

const SLOTS: Record<
  Slot,
  { kind: AssetKind; label: string; hint: string; icon: typeof Film; dialogTitle: string }
> = {
  intro: {
    kind: 'video',
    label: 'Thêm intro',
    hint: 'Đoạn mở đầu, chèn trước video chính',
    icon: Film,
    dialogTitle: 'Chọn video intro',
  },
  outro: {
    kind: 'video',
    label: 'Thêm outro',
    hint: 'Đoạn kết, chèn sau video chính',
    icon: Film,
    dialogTitle: 'Chọn video outro',
  },
  logo: {
    kind: 'image',
    label: 'Thêm logo',
    hint: 'Logo/watermark chồng lên video',
    icon: ImageIcon,
    dialogTitle: 'Chọn ảnh logo / watermark',
  },
  music: {
    kind: 'audio',
    label: 'Thêm nhạc nền',
    hint: 'Nhạc nền phát cùng giọng đọc',
    icon: Music,
    dialogTitle: 'Chọn nhạc nền',
  },
}

/**
 * Put a file from the library onto the timeline. Each button knows which clip shape to build —
 * the user does not have to remember that a logo is an "image" track while an intro is the first clip of the
 * "video" track.
 */
export function AssetPanel() {
  const [openSlot, setOpenSlot] = useState<Slot | null>(null)
  const operations = useEditorStore((s) => s.operations)
  const addClipToTrack = useEditorStore((s) => s.addClipToTrack)
  const setOperations = useEditorStore((s) => s.setOperations)

  function handleSelect(slot: Slot, asset: Asset) {
    if (slot === 'logo') {
      // Do not set start/end: the logo shows for the whole video (the backend treats this as the default).
      addClipToTrack('image', {
        source: asset.path,
        x: 0.85,
        y: 0.12,
        width: 0.15,
        opacity: 0.85,
      })
      toast.success(`Đã thêm logo "${asset.name}"`)
      return
    }

    if (slot === 'music') {
      addClipToTrack(
        'audio',
        {
          source: asset.path,
          start: 0,
          end: DEFAULT_CLIP_SECONDS,
          track_start: 0,
          // Much quieter than the narration — background music as loud as the dialogue makes the speech hard to hear.
          volume: 0.2,
        },
        'music'
      )
      toast.success(`Đã thêm nhạc nền "${asset.name}"`)
      return
    }

    // intro/outro: insert into the existing video track, exactly at the start or the end.
    const videoIndex = operations.tracks.findIndex((t) => t.type === 'video')
    const clip = { source: asset.path, start: 0, end: DEFAULT_CLIP_SECONDS }

    if (videoIndex < 0) {
      addClipToTrack('video', clip)
      toast.success(`Đã thêm "${asset.name}"`)
      return
    }

    const tracks: TimelineTrack[] = operations.tracks.map((track, i) =>
      i === videoIndex
        ? {
            ...track,
            clips: slot === 'intro' ? [clip, ...track.clips] : [...track.clips, clip],
          }
        : track
    )
    setOperations({ tracks })
    toast.success(`Đã thêm ${slot} "${asset.name}"`)
  }

  const active = openSlot ? SLOTS[openSlot] : null

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>Thêm vào video</CardTitle>
        <CardDescription>
          Logo, intro/outro và nhạc nền dùng lại được cho mọi video — tải lên một lần.
        </CardDescription>
      </CardHeader>
      <CardContent className='grid gap-2 sm:grid-cols-2'>
        {(Object.keys(SLOTS) as Slot[]).map((slot) => {
          const { label, hint, icon: Icon } = SLOTS[slot]
          return (
            <Button
              key={slot}
              type='button'
              variant='outline'
              className='h-auto justify-start gap-2 py-2 text-start'
              onClick={() => setOpenSlot(slot)}
            >
              <Icon className='size-4 shrink-0' />
              <span className='min-w-0'>
                <span className='block text-sm'>{label}</span>
                <span className='block text-xs font-normal text-muted-foreground'>{hint}</span>
              </span>
            </Button>
          )
        })}
      </CardContent>

      {active && openSlot && (
        <AssetPicker
          open
          kind={active.kind}
          title={active.dialogTitle}
          description='Chọn file có sẵn trong kho, hoặc tải file mới lên.'
          onSelect={(asset) => handleSelect(openSlot, asset)}
          onOpenChange={(open) => {
            if (!open) setOpenSlot(null)
          }}
        />
      )}
    </Card>
  )
}
