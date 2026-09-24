import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { getApiErrorMessage, getAppSettings, updateAppSettings } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { ContentSection } from '../components/content-section'

/**
 * Cài đặt lồng tiếng. Hiện chỉ có công tắc "Phân vai người nói": mặc định TẮT
 * vì kết quả chưa ổn định (video 1 người dẫn vẫn có thể ra hàng chục "người
 * nói"). Tắt thì ẩn bước phân vai + tab Giọng đọc, và lồng tiếng dùng 1 giọng
 * chung. Lưu qua `PUT /api/settings` như trang Tải xuống.
 */
export function SettingsDubbing() {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['app-settings'],
    queryFn: getAppSettings,
  })

  const update = useMutation({
    mutationFn: updateAppSettings,
    onSuccess: (result) => {
      queryClient.setQueryData(['app-settings'], result)
      toast.success('Đã lưu — áp dụng ngay, không cần khởi động lại.')
    },
    onError: (error) =>
      toast.error(getApiErrorMessage(error, 'Không lưu được cài đặt.')),
  })

  return (
    <ContentSection
      title='Lồng tiếng'
      desc='Tuỳ chọn cho bước tách lời thoại và lồng tiếng.'
    >
      {isLoading || !data ? (
        <p className='flex items-center gap-2 text-muted-foreground'>
          <Loader2 className='size-4 animate-spin' />
          Đang tải...
        </p>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>Phân vai người nói</CardTitle>
            <CardDescription>
              Tự nhận diện có bao nhiêu người nói trong video để gán giọng đọc
              riêng cho từng vai. Tính năng còn thử nghiệm: video chỉ có 1
              người dẫn vẫn có thể bị tách thành rất nhiều &quot;người nói&quot;.
              Tắt thì lồng tiếng bằng 1 giọng chung.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className='flex items-center gap-3'>
              <Switch
                id='speaker-diarization'
                checked={data.speaker_diarization_enabled}
                disabled={update.isPending}
                onCheckedChange={(checked) =>
                  update.mutate({ speaker_diarization_enabled: checked })
                }
              />
              <Label htmlFor='speaker-diarization'>
                Bật phân vai người nói
              </Label>
            </div>
          </CardContent>
        </Card>
      )}
    </ContentSection>
  )
}
