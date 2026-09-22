import { Eraser, Square, Type } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { getFonts } from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { useEditorStore } from './store'

/** Vùng che mặc định: góc trên phải, nơi Bilibili/Douyin thường đóng logo. */
const DEFAULT_LOGO_REGION = { x: 0.72, y: 0.03, width: 0.25, height: 0.12 }

/** Phụ đề gốc thường nằm giữa-dưới khung. */
const DEFAULT_SUBTITLE_REGION = { x: 0.1, y: 0.82, width: 0.8, height: 0.14 }

export function SubtitleBoxPanel() {
  // Chỉ subscribe đúng track "overlay" — trước đây lấy cả `s.operations` khiến
  // panel này render lại mỗi khi bất kỳ track nào đổi (vd kéo watermark),
  // dù chỉ cần biết mỗi track phụ đề.
  const overlayIndex = useEditorStore((s) =>
    s.operations.tracks.findIndex((t) => t.type === 'overlay')
  )
  const overlayTrack = useEditorStore(
    (s) => s.operations.tracks.find((t) => t.type === 'overlay') ?? null
  )
  const addClipToTrack = useEditorStore((s) => s.addClipToTrack)
  const updateTrackClips = useEditorStore((s) => s.updateTrackClips)

  // Font cố định (không đổi lúc chạy) — không cần refetch lại mỗi lần mở editor.
  const { data: fonts } = useQuery({
    queryKey: ['fonts'],
    queryFn: getFonts,
    staleTime: Infinity,
  })
  // Khung phụ đề + kiểu chữ áp cho CẢ track: từng câu một kiểu khác nhau thì
  // phụ đề nhảy loạn giữa các câu.
  const currentBoxWidth = overlayTrack?.clips[0]?.box_width ?? 0
  const currentFontFamily = overlayTrack?.clips[0]?.font_family ?? ''
  const currentFontColor = overlayTrack?.clips[0]?.font_color ?? 'FFFFFF'
  const currentBold = overlayTrack?.clips[0]?.bold ?? false

  function addBlurRegion(region: typeof DEFAULT_LOGO_REGION, label: string) {
    addClipToTrack('blur', { ...region, strength: 20, mode: 'blur' })
    toast.success(
      `Đã thêm vùng che ${label} — kéo trên khung xem trước để chỉnh`
    )
  }

  function setBoxWidth(width: number) {
    if (!overlayTrack) {
      toast.error('Chưa có phụ đề. Bấm "Dùng gợi ý AI" để nạp phụ đề đã dịch.')
      return
    }
    updateTrackClips(overlayIndex, { box_width: width || undefined })
  }

  function setStyle(patch: { font_family?: string; font_color?: string; bold?: boolean }) {
    if (!overlayTrack) {
      toast.error('Chưa có phụ đề. Bấm "Dùng gợi ý AI" để nạp phụ đề đã dịch.')
      return
    }
    updateTrackClips(overlayIndex, patch)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>Che & khung phụ đề</CardTitle>
        <CardDescription>
          Che logo hoặc phụ đề tiếng Trung có sẵn, và giới hạn vùng hiện phụ đề
          mới.
        </CardDescription>
      </CardHeader>
      <CardContent className='space-y-4'>
        <div className='space-y-2'>
          <Label className='text-xs text-muted-foreground'>
            Thêm vùng làm mờ
          </Label>
          <div className='flex flex-wrap gap-2'>
            <Button
              type='button'
              size='sm'
              variant='outline'
              className='gap-1'
              onClick={() => addBlurRegion(DEFAULT_LOGO_REGION, 'logo')}
            >
              <Eraser className='size-3.5' />
              Che logo (góc trên phải)
            </Button>
            <Button
              type='button'
              size='sm'
              variant='outline'
              className='gap-1'
              onClick={() =>
                addBlurRegion(DEFAULT_SUBTITLE_REGION, 'phụ đề gốc')
              }
            >
              <Eraser className='size-3.5' />
              Che phụ đề tiếng Trung
            </Button>
          </div>
          <p className='text-xs text-muted-foreground'>
            Vùng che hiện viền vàng trên khung xem trước — kéo để di chuyển, kéo
            góc dưới-phải để đổi kích thước.
          </p>
        </div>

        <div className='space-y-2'>
          <Label className='flex items-center gap-1 text-xs text-muted-foreground'>
            <Square className='size-3' />
            Khung hiện phụ đề
          </Label>
          <div className='flex flex-wrap gap-2'>
            {[
              { label: 'Tự do (cả khung)', value: 0 },
              { label: 'Hẹp (50%)', value: 0.5 },
              { label: 'Vừa (70%)', value: 0.7 },
              { label: 'Rộng (90%)', value: 0.9 },
            ].map((option) => (
              <Button
                key={option.value}
                type='button'
                size='sm'
                variant={
                  currentBoxWidth === option.value ? 'default' : 'outline'
                }
                onClick={() => setBoxWidth(option.value)}
              >
                {option.label}
              </Button>
            ))}
          </div>
          <p className='flex items-start gap-1 text-xs text-muted-foreground'>
            <Type className='mt-0.5 size-3 shrink-0' />
            Câu dài sẽ tự chia dòng cho vừa khung. Không giới hạn thì câu dài bị
            cắt mất hai đầu.
          </p>
        </div>

        <div className='space-y-2'>
          <Label className='text-xs text-muted-foreground'>Kiểu chữ phụ đề</Label>
          <div className='flex flex-wrap items-center gap-2'>
            <select
              className='h-8 rounded-md border bg-transparent px-2 text-xs'
              value={currentFontFamily}
              onChange={(e) => setStyle({ font_family: e.target.value || undefined })}
            >
              <option value=''>Mặc định (Be Vietnam Pro)</option>
              {fonts?.map((font) => (
                <option key={font.id} value={font.id}>
                  {font.label}
                </option>
              ))}
            </select>
            <input
              type='color'
              className='h-8 w-10 cursor-pointer rounded-md border bg-transparent p-0.5'
              value={`#${currentFontColor}`}
              onChange={(e) => setStyle({ font_color: e.target.value.replace('#', '') })}
            />
            <label className='flex items-center gap-1 text-xs'>
              <input
                type='checkbox'
                checked={currentBold}
                onChange={(e) => setStyle({ bold: e.target.checked })}
              />
              Đậm
            </label>
          </div>
          <p className='text-xs text-muted-foreground'>
            Áp cho toàn bộ câu phụ đề trong track — giữ đồng nhất giữa các câu.
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
