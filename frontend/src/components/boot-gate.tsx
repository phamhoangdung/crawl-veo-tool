import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { APP_NAME } from '@/config/app'
import {
  API_BASE_URL,
  api,
  getFollowedCategories,
  getTrendingCategories,
} from '@/lib/api'
import { BOOT_STEPS, bootPercent, type BootStepId } from '@/lib/boot-steps'
import {
  CATEGORIES_QUERY_KEY,
  FOLLOWED_CATEGORIES_QUERY_KEY,
} from '@/lib/query-keys'
import { Button } from '@/components/ui/button'
import { BrandLoader } from './brand-loader'

const POLL_INTERVAL_MS = 500
const BACKEND_TIMEOUT_MS = 120_000
/** Giữ splash tối thiểu ngần này để logo không chớp rồi biến mất khi backend đã sẵn. */
const MIN_VISIBLE_MS = 600
const FADE_MS = 250

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

async function waitForBackend(isCancelled: () => boolean): Promise<boolean> {
  const deadline = Date.now() + BACKEND_TIMEOUT_MS
  while (!isCancelled() && Date.now() < deadline) {
    try {
      await api.get('/health', { timeout: 3000 })
      return true
    } catch {
      await sleep(POLL_INTERVAL_MS)
    }
  }
  return false
}

type Phase = 'booting' | 'failed' | 'leaving' | 'ready'

/**
 * Chặn giao diện cho tới khi backend trả lời `/health` và dữ liệu nền tảng đã
 * nạp vào cache. Bản đóng gói bật backend chậm hơn cửa sổ app, nên không có cổng
 * này người dùng sẽ thấy "Network Error" ngay lần mở đầu tiên.
 *
 * Prefetch lỗi KHÔNG chặn: trang tự fetch lại và báo lỗi theo cách riêng của nó.
 */
export function BootGate({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const [phase, setPhase] = useState<Phase>('booting')
  const [done, setDone] = useState<ReadonlySet<BootStepId>>(new Set())
  const [attempt, setAttempt] = useState(0)
  const startedAt = useRef(0)

  const markDone = useCallback((id: BootStepId) => {
    setDone((prev) => new Set(prev).add(id))
  }, [])

  const retry = () => {
    setPhase('booting')
    setDone(new Set())
    setAttempt((n) => n + 1)
  }

  useEffect(() => {
    let cancelled = false
    startedAt.current = Date.now()

    void (async () => {
      const up = await waitForBackend(() => cancelled)
      if (cancelled) return
      if (!up) {
        setPhase('failed')
        return
      }
      markDone('backend')

      await Promise.all([
        queryClient
          .prefetchQuery({
            queryKey: CATEGORIES_QUERY_KEY,
            queryFn: getTrendingCategories,
          })
          .finally(() => !cancelled && markDone('categories')),
        queryClient
          .prefetchQuery({
            queryKey: FOLLOWED_CATEGORIES_QUERY_KEY,
            queryFn: getFollowedCategories,
          })
          .finally(() => !cancelled && markDone('followed')),
      ])
      if (cancelled) return

      const remaining = MIN_VISIBLE_MS - (Date.now() - startedAt.current)
      if (remaining > 0) await sleep(remaining)
      if (cancelled) return
      setPhase('leaving')
      await sleep(FADE_MS)
      if (!cancelled) setPhase('ready')
    })()

    return () => {
      cancelled = true
    }
  }, [attempt, queryClient, markDone])

  if (phase === 'ready') return <>{children}</>

  const currentLabel =
    BOOT_STEPS.find((s) => !done.has(s.id))?.label ?? 'Sẵn sàng!'

  return (
    <>
      {phase === 'leaving' && children}
      <div
        className={`fixed inset-0 z-[200] flex flex-col items-center justify-center gap-8 bg-background transition-opacity ${
          phase === 'leaving' ? 'pointer-events-none opacity-0' : 'opacity-100'
        }`}
        style={{ transitionDuration: `${FADE_MS}ms` }}
      >
        {phase === 'failed' ? (
          <div className='max-w-sm space-y-4 text-center'>
            <h1 className='text-xl font-semibold'>
              Không kết nối được dịch vụ nền
            </h1>
            <p className='text-sm text-muted-foreground'>
              {APP_NAME} không nhận được phản hồi từ backend sau{' '}
              {BACKEND_TIMEOUT_MS / 1000} giây. Kiểm tra backend đang chạy (địa
              chỉ {API_BASE_URL}) hoặc phần mềm diệt virus có chặn không, rồi thử
              lại.
            </p>
            <p className='text-xs break-all text-muted-foreground'>
              Nhật ký lỗi: %APPDATA%\VieDubStudio\logs\backend.log
            </p>
            <Button onClick={retry}>Thử lại</Button>
          </div>
        ) : (
          <>
            <h1 className='sr-only'>{APP_NAME}</h1>
            <BrandLoader
              size='lg'
              label={currentLabel}
              percent={done.has('backend') ? bootPercent(done) : undefined}
            />
          </>
        )}
      </div>
    </>
  )
}
