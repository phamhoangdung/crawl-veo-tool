import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { getCategoryHistory, getCategoryStats } from '@/lib/api'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

/** Màu đủ tương phản trong cả nền sáng lẫn tối. */
const SERIES_COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
  '#e8845d',
  '#5db8e8',
  '#b45de8',
]

function formatCompact(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`
  return String(value)
}

function formatTime(iso: string) {
  const date = new Date(iso)
  return date.toLocaleString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

type ChartRow = { time: string } & Record<string, number | string>

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}) {
  if (!active || !payload?.length) return null

  const sorted = [...payload].sort((a, b) => b.value - a.value)

  return (
    <div className='rounded-lg border bg-background p-3 text-xs shadow-md'>
      <p className='mb-1.5 font-medium'>{label}</p>
      <ul className='space-y-1'>
        {sorted.map((entry) => (
          <li key={entry.name} className='flex items-center justify-between gap-4'>
            <span className='flex items-center gap-1.5 text-muted-foreground'>
              <span
                className='size-2 rounded-full'
                style={{ backgroundColor: entry.color }}
              />
              {entry.name}
            </span>
            <span className='font-medium'>{entry.value.toLocaleString('vi-VN')}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function CategoryChart({ rids }: { rids: number[] }) {
  const sortedRids = useMemo(() => [...rids].sort((a, b) => a - b), [rids])

  // Gọi stats để ghi thêm 1 điểm lịch sử cho lần mở trang này; kết quả dùng làm
  // dự phòng hiển thị khi lịch sử còn quá ít điểm.
  const statsQuery = useQuery({
    queryKey: ['trending', 'stats', sortedRids],
    queryFn: () => getCategoryStats(sortedRids),
    enabled: sortedRids.length > 0,
    staleTime: 5 * 60 * 1000,
  })

  const historyQuery = useQuery({
    queryKey: ['trending', 'history', sortedRids],
    queryFn: () => getCategoryHistory(sortedRids),
    enabled: sortedRids.length > 0 && statsQuery.isSuccess,
    staleTime: 60 * 1000,
  })

  const { rows, series } = useMemo(() => {
    const histories = historyQuery.data ?? []
    const names = new Map<number, string>(histories.map((h) => [h.rid, h.name]))

    // Gom điểm của mọi chuyên mục theo mốc thời gian để recharts vẽ nhiều đường
    // trên cùng một trục X.
    const byTime = new Map<string, ChartRow>()
    for (const history of histories) {
      for (const point of history.points) {
        const key = point.captured_at
        const row = byTime.get(key) ?? { time: formatTime(key) }
        row[history.name] = point.total_plays
        byTime.set(key, row)
      }
    }

    const sortedRows = [...byTime.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([, row]) => row)

    return { rows: sortedRows, series: [...names.values()] }
  }, [historyQuery.data])

  if (sortedRids.length === 0) return null

  const isLoading = statsQuery.isLoading || historyQuery.isLoading
  const hasTrend = rows.length >= 2

  return (
    <Card>
      <CardHeader>
        <CardTitle>Chủ đề đang được quan tâm</CardTitle>
        <CardDescription>
          {hasTrend
            ? 'Tổng lượt xem của các video đang lên xu hướng, theo thời gian.'
            : 'Số liệu được ghi lại mỗi lần bạn mở trang này — mở thêm vài lần trong ngày để thấy đường xu hướng.'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading && <Skeleton className='h-72 w-full' />}

        {statsQuery.isError && (
          <p className='text-sm text-destructive'>
            Không tải được số liệu. Kiểm tra backend đang chạy.
          </p>
        )}

        {!isLoading && !statsQuery.isError && (
          <>
            {hasTrend ? (
              <div className='h-72 w-full'>
                <ResponsiveContainer width='100%' height='100%'>
                  <LineChart data={rows} margin={{ left: 4, right: 12, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray='3 3' opacity={0.3} vertical={false} />
                    <XAxis
                      dataKey='time'
                      tickLine={false}
                      axisLine={false}
                      fontSize={11}
                      minTickGap={24}
                    />
                    <YAxis
                      tickFormatter={formatCompact}
                      tickLine={false}
                      axisLine={false}
                      fontSize={11}
                      width={48}
                    />
                    <Tooltip content={<ChartTooltip />} />
                    {series.map((name, index) => (
                      <Line
                        key={name}
                        type='monotone'
                        dataKey={name}
                        stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4 }}
                        connectNulls
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <CurrentSnapshot stats={statsQuery.data ?? []} />
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

/** Chưa đủ điểm để vẽ đường — hiển thị số liệu hiện tại dạng thanh ngang. */
function CurrentSnapshot({
  stats,
}: {
  stats: Array<{ rid: number; name: string; total_plays: number; avg_plays: number }>
}) {
  if (stats.length === 0) {
    return (
      <p className='text-sm text-muted-foreground'>
        Chưa có số liệu cho các chuyên mục đã chọn.
      </p>
    )
  }

  const max = Math.max(...stats.map((s) => s.total_plays), 1)

  return (
    <ul className='space-y-3'>
      {stats.map((item, index) => (
        <li key={item.rid} className='space-y-1'>
          <div className='flex items-baseline justify-between gap-4 text-sm'>
            <span className='truncate'>{item.name}</span>
            <span className='shrink-0 text-muted-foreground tabular-nums'>
              {item.total_plays.toLocaleString('vi-VN')}
            </span>
          </div>
          <div className='h-2 overflow-hidden rounded-full bg-muted'>
            <div
              className='h-full rounded-full'
              style={{
                width: `${(item.total_plays / max) * 100}%`,
                backgroundColor: SERIES_COLORS[index % SERIES_COLORS.length],
              }}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}
