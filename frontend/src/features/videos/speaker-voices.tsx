import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  getAvailableVoices,
  updateSpeakerVoices,
  type TranscriptSegment,
  type VoiceRef,
} from '@/lib/api'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

type Props = {
  videoId: number
  segments: TranscriptSegment[]
  speakerVoices: Record<string, VoiceRef>
}

function genderLabel(gender: string) {
  if (gender === 'female') return 'nữ'
  if (gender === 'male') return 'nam'
  return '?'
}

function voiceKey(voice: VoiceRef) {
  return `${voice.provider}::${voice.voice_id}`
}

/** Tab "Giọng đọc" — chọn giọng riêng cho từng vai đã phát hiện được ở bước
 * "Phân vai người nói". Vai nào không gán thì `dubVideo` dùng giọng mặc định
 * chung, không bắt buộc phải điền hết. */
export function SpeakerVoices({ videoId, segments, speakerVoices }: Props) {
  const queryClient = useQueryClient()

  const { data: voices } = useQuery({
    queryKey: ['voices', videoId],
    queryFn: () => getAvailableVoices(videoId),
  })

  // Tối đa 2 câu mẫu mỗi vai — đủ để người dùng nhận ra "đây là ai" mà không
  // phải cuộn qua cả bảng phụ đề.
  const speakers = useMemo(() => {
    const bySpeaker = new Map<string, TranscriptSegment[]>()
    for (const segment of segments) {
      if (!segment.speaker) continue
      const list = bySpeaker.get(segment.speaker) ?? []
      if (list.length < 2) list.push(segment)
      bySpeaker.set(segment.speaker, list)
    }
    return Array.from(bySpeaker.entries()).sort(([a], [b]) => a.localeCompare(b))
  }, [segments])

  const save = useMutation({
    mutationFn: (next: Record<string, VoiceRef>) => updateSpeakerVoices(videoId, next),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['video', videoId] })
      toast.success('Đã lưu giọng đọc theo vai.')
    },
    onError: () => toast.error('Không lưu được giọng đọc.'),
  })

  function assignVoice(speaker: string, value: string) {
    if (!value) {
      const next = { ...speakerVoices }
      delete next[speaker]
      save.mutate(next)
      return
    }
    const [provider, voiceId] = value.split('::')
    save.mutate({ ...speakerVoices, [speaker]: { provider, voice_id: voiceId } })
  }

  if (speakers.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className='text-base'>Giọng đọc theo vai</CardTitle>
          <CardDescription>
            Chạy bước &quot;Phân vai người nói&quot; ở tab Xử lý trước để thấy
            danh sách vai ở đây. Bỏ qua bước này thì video vẫn lồng tiếng bình
            thường bằng 1 giọng chung.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>Giọng đọc theo vai ({speakers.length})</CardTitle>
        <CardDescription>
          Chọn giọng đọc riêng cho từng vai đã phát hiện được. Vai nào chưa
          chọn sẽ dùng giọng mặc định chung.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-4'>
        {speakers.map(([speaker, samples], index) => {
          const current = speakerVoices[speaker]
          const currentValue = current ? voiceKey(current) : ''
          return (
            <div key={speaker} className='space-y-2 rounded-lg border p-3'>
              <p className='text-sm font-medium'>
                Vai {index + 1} ({speaker})
              </p>
              <ul className='space-y-1'>
                {samples.map((s, i) => (
                  <li key={i} className='text-xs text-muted-foreground italic'>
                    &quot;{s.translated_text || s.text}&quot;
                  </li>
                ))}
              </ul>
              <select
                className='h-8 w-full rounded-md border bg-transparent px-2 text-sm'
                value={currentValue}
                disabled={save.isPending}
                onChange={(e) => assignVoice(speaker, e.target.value)}
              >
                <option value=''>Giọng mặc định chung</option>
                {(voices ?? []).map((v) => (
                  <option key={voiceKey(v)} value={voiceKey(v)}>
                    {v.name} ({genderLabel(v.gender)})
                  </option>
                ))}
              </select>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
