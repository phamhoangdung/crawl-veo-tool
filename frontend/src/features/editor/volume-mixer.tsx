import { Music, Mic, Volume2, VolumeX } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { useEditorStore } from './store'

/** Nhãn theo vai trò track — `role` do gợi ý AI đặt khi dựng timeline. */
const ROLE_META: Record<string, { label: string; icon: typeof Mic }> = {
  voice: { label: 'Giọng đọc', icon: Mic },
  music: { label: 'Nhạc nền', icon: Music },
}

function volumeLabel(volume: number) {
  if (volume === 0) return 'Tắt tiếng'
  return `${Math.round(volume * 100)}%`
}

/**
 * Chỉnh âm lượng từng track audio, luôn hiện sẵn — khác `ClipInspector` phải
 * chọn clip mới thấy. Đây là thao tác dùng thường xuyên nhất khi trộn tiếng.
 */
export function VolumeMixer() {
  const operations = useEditorStore((s) => s.operations)
  const updateClip = useEditorStore((s) => s.updateClip)

  const audioTracks = operations.tracks
    .map((track, trackIndex) => ({ track, trackIndex }))
    .filter(({ track }) => track.type === 'audio')

  if (audioTracks.length === 0) return null

  return (
    <div className='space-y-3'>
      {audioTracks.map(({ track, trackIndex }) => {
        const clip = track.clips[0]
        if (!clip) return null

        const volume = clip.volume ?? 1
        const meta = ROLE_META[track.role ?? ''] ?? {
          label: track.role ?? 'Âm thanh',
          icon: Volume2,
        }
        const Icon = meta.icon
        const isMuted = volume === 0

        // Chỉnh cả clip trong track: các track audio ở đây đều 1 clip trải dài
        // toàn video, nên đổi cùng lúc là đúng ý người dùng.
        const setVolume = (next: number) => {
          track.clips.forEach((_, clipIndex) => {
            updateClip(trackIndex, clipIndex, { volume: next })
          })
        }

        return (
          <div key={trackIndex} className='flex items-center gap-3'>
            <Label className='flex w-28 shrink-0 items-center gap-1.5 text-xs'>
              <Icon className='size-3.5 text-muted-foreground' />
              {meta.label}
            </Label>

            <Button
              size='icon'
              variant='ghost'
              className='size-7 shrink-0'
              title={isMuted ? 'Bật tiếng' : 'Tắt tiếng'}
              onClick={() => setVolume(isMuted ? 1 : 0)}
            >
              {isMuted ? (
                <VolumeX className='size-3.5 text-muted-foreground' />
              ) : (
                <Volume2 className='size-3.5' />
              )}
            </Button>

            <input
              type='range'
              min={0}
              max={2}
              step={0.05}
              value={volume}
              onChange={(e) => setVolume(Number(e.target.value))}
              aria-label={`Âm lượng ${meta.label}`}
              className='h-1.5 flex-1 cursor-pointer accent-primary'
            />

            <span className='w-14 shrink-0 text-end text-xs tabular-nums text-muted-foreground'>
              {volumeLabel(volume)}
            </span>
          </div>
        )
      })}

      <p className='text-xs text-muted-foreground'>
        Trên 100% là khuếch đại — quá tay có thể gây rè. Nhạc nền thường để
        20–40% để không át giọng đọc.
      </p>
    </div>
  )
}
