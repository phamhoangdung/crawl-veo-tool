import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { getApiErrorMessage, getAppSettings, updateAppSettings } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ContentSection } from '../components/content-section'

/** A native `<select>` instead of the Radix `Select` — it is just "pick 1 number from a
 * fixed list", with no need for the advanced features (search, grouping...) of Radix, and it
 * avoids depending on 1 more component for exactly these 2 pickers. Same classes as
 * `Input` to keep the look consistent.
 *
 * `aria-label` instead of a separate hidden `<Label>`: the `CardTitle` above already shows
 * the field name visually, adding an sr-only `<Label>` with the same text would create 2 elements
 * with the same accessible name — a nuisance when tests query by text/role. */
function NumberSelect({
  value,
  options,
  suffix,
  disabled,
  onChange,
  ariaLabel,
}: {
  value: number
  options: number[]
  suffix: string
  disabled?: boolean
  onChange: (value: number) => void
  ariaLabel: string
}) {
  return (
    <select
      aria-label={ariaLabel}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(Number(e.target.value))}
      className={cn(
        'flex h-9 w-32 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none',
        'focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50',
        'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
        'dark:bg-input/30'
      )}
    >
      {options.map((n) => (
        <option key={n} value={n}>
          {n} {suffix}
        </option>
      ))}
    </select>
  )
}

const CONNECTIONS_OPTIONS = [1, 2, 4, 8]
const MAX_VIDEOS_OPTIONS = [1, 2, 3, 5, 10]

/**
 * Download speed settings — Phase 21. The first page of the tool with settings
 * really saved via `PUT /api/settings` (the other pages in /settings are still
 * demos of the shadcn-admin template, untouched).
 *
 * The 2 settings sit side by side ON PURPOSE: "Threads per video" is a ceiling for the WHOLE APP,
 * not for each video — setting 8 then downloading 3 videos at once is NOT 24
 * connections, the 3 videos share exactly 8 (see the explanation in the card).
 */
export function SettingsDownloads() {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['app-settings'],
    queryFn: getAppSettings,
  })

  const update = useMutation({
    mutationFn: updateAppSettings,
    onSuccess: (result) => {
      queryClient.setQueryData(['app-settings'], result)
      toast.success('Đã lưu — áp dụng ngay cho lượt tải tiếp theo, không cần khởi động lại.')
    },
    onError: (error) =>
      toast.error(getApiErrorMessage(error, 'Không lưu được cài đặt.')),
  })

  return (
    <ContentSection
      title='Tải xuống'
      desc='Điều chỉnh tốc độ và số lượng video tải cùng lúc từ Bilibili.'
    >
      {isLoading || !data ? (
        <p className='flex items-center gap-2 text-muted-foreground'>
          <Loader2 className='size-4 animate-spin' />
          Đang tải...
        </p>
      ) : (
        <div className='space-y-4'>
          <Card>
            <CardHeader>
              <CardTitle className='text-base'>Số luồng mỗi video</CardTitle>
              <CardDescription>
                Chia mỗi video thành nhiều phần tải song song qua HTTP Range —
                đo thật: 8 luồng nhanh gấp ~2,9 lần 1 luồng trên đường truyền
                tốt. Mạng yếu hoặc hay đứt thì để 1 (mặc định, đúng hành vi cũ).
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className='flex items-center gap-3'>
                <NumberSelect
                  ariaLabel='Số luồng mỗi video'
                  value={data.download_connections}
                  options={CONNECTIONS_OPTIONS}
                  suffix='luồng'
                  disabled={update.isPending}
                  onChange={(n) => update.mutate({ download_connections: n })}
                />
                <p className='text-xs text-muted-foreground'>
                  Đây là trần dùng chung cho <strong>cả app</strong>, không
                  phải riêng từng video — 3 video tải cùng lúc sẽ tự chia
                  nhau đúng số luồng này, không cộng dồn.
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className='text-base'>Số video tải cùng lúc</CardTitle>
              <CardDescription>
                Bấm tải nhiều video một lúc ở màn Khám phá thì tối đa bao
                nhiêu video được tải THẬT SỰ song song — video vượt mức này
                tự xếp hàng, không tải bị bỏ sót.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className='flex items-center gap-3'>
                <NumberSelect
                  ariaLabel='Số video tải cùng lúc'
                  value={data.download_max_videos}
                  options={MAX_VIDEOS_OPTIONS}
                  suffix='video'
                  disabled={update.isPending}
                  onChange={(n) => update.mutate({ download_max_videos: n })}
                />
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </ContentSection>
  )
}
