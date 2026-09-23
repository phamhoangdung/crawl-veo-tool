import { type ImgHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'
import logoUrl from './logo.png'

export function Logo({
  className,
  ...props
}: ImgHTMLAttributes<HTMLImageElement>) {
  return (
    <img
      id='viedub-logo'
      src={logoUrl}
      alt='VieDub Studio'
      className={cn('size-6 object-contain', className)}
      {...props}
    />
  )
}
