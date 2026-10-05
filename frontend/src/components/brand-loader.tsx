import { Logo } from '@/assets/logo'
import { cn } from '@/lib/utils'

type BrandLoaderProps = {
  /** The description line below; defaults to "Đang tải...". */
  label?: string
  /** 0-100. With a value → a real progress bar + shows %; left empty → an indeterminate bar. */
  percent?: number
  /** `sm` is the compact form inside a panel, `lg` is for the whole screen. */
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const LOGO_SIZE = { sm: 'size-7', md: 'size-16', lg: 'size-24' } as const

export function BrandLoader({
  label = 'Đang tải...',
  percent,
  size = 'md',
  className,
}: BrandLoaderProps) {
  if (size === 'sm') {
    return (
      <div
        role='status'
        aria-live='polite'
        className={cn(
          'flex items-center gap-2 text-sm text-muted-foreground',
          className
        )}
      >
        <Logo className={cn(LOGO_SIZE.sm, 'brand-logo-pulse')} />
        <span>{label}</span>
        {percent !== undefined && (
          <span className='tabular-nums'>{Math.round(percent)}%</span>
        )}
      </div>
    )
  }

  const clamped =
    percent === undefined ? undefined : Math.min(100, Math.max(0, percent))

  return (
    <div
      role='status'
      aria-live='polite'
      className={cn('flex flex-col items-center gap-4', className)}
    >
      <Logo className={cn(LOGO_SIZE[size], 'brand-logo-pulse')} />
      <div className='w-64 space-y-2'>
        <div
          role='progressbar'
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={clamped}
          className='relative h-1.5 w-full overflow-hidden rounded-full bg-muted'
        >
          {clamped === undefined ? (
            <div className='brand-bar-sweep absolute inset-y-0 w-1/3 rounded-full bg-primary' />
          ) : (
            <div
              className='h-full rounded-full bg-primary transition-[width] duration-300 ease-out'
              style={{ width: `${clamped}%` }}
            />
          )}
        </div>
        <p className='text-center text-sm text-muted-foreground'>
          {label}
          {clamped !== undefined && (
            <span className='ms-2 tabular-nums'>{Math.round(clamped)}%</span>
          )}
        </p>
      </div>
    </div>
  )
}

/** Covers the whole screen when an action forces the user to wait. */
export function LoadingOverlay({
  open,
  ...props
}: BrandLoaderProps & { open: boolean }) {
  if (!open) return null
  return (
    <div className='fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm'>
      <BrandLoader size='lg' {...props} />
    </div>
  )
}

/** A loading content area: centered, tall enough to avoid layout jumps. */
export function PageLoader({ label }: { label?: string }) {
  return (
    <div className='flex min-h-[40vh] items-center justify-center'>
      <BrandLoader label={label} />
    </div>
  )
}
