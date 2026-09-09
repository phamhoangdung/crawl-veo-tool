import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { IMAGE_MODELS, type StudioSettings } from '../types'

const VARIANT_OPTIONS = [1, 2, 4]

interface Props {
  settings: StudioSettings
  onChange: (settings: StudioSettings) => void
}

export function GenerationSettingsPanel({ settings, onChange }: Props) {
  const patch = (partial: Partial<StudioSettings>) =>
    onChange({ ...settings, ...partial })

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>Cấu hình</CardTitle>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div className='space-y-1'>
          <Label htmlFor='image-model'>Model ảnh</Label>
          <Select
            value={settings.imageModel}
            onValueChange={(value) => patch({ imageModel: value })}
          >
            <SelectTrigger id='image-model'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {IMAGE_MODELS.map((model) => (
                <SelectItem key={model.id} value={model.id}>
                  {model.label} — ${model.pricePerImage.toFixed(3)}/ảnh
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className='space-y-1'>
          <Label htmlFor='variant-count'>Số ảnh mỗi lần sinh</Label>
          <Select
            value={String(settings.variantCount)}
            onValueChange={(value) => patch({ variantCount: Number(value) })}
          >
            <SelectTrigger id='variant-count'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {VARIANT_OPTIONS.map((count) => (
                <SelectItem key={count} value={String(count)}>
                  {count} ảnh
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className='text-muted-foreground text-xs'>
            Sinh nhiều ảnh để chọn thì rẻ; video thì luôn sinh 1 vì đắt hơn ảnh hàng chục
            lần.
          </p>
        </div>

        <div className='space-y-1'>
          <Label htmlFor='output-prefix'>Tên file theo tập (tuỳ chọn)</Label>
          <Input
            id='output-prefix'
            placeholder='vd EP001'
            value={settings.outputPrefix}
            onChange={(e) => patch({ outputPrefix: e.target.value })}
          />
          <p className='text-muted-foreground text-xs'>
            {settings.outputPrefix
              ? `File sẽ đặt tên ${settings.outputPrefix}_001, ${settings.outputPrefix}_002...`
              : 'Để trống thì đặt tên tự động.'}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
