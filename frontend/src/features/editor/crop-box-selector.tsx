import { useRef } from 'react'
import type { CropBox } from '@/lib/api'

interface CropBoxSelectorProps {
  videoWidth: number
  videoHeight: number
  value: CropBox
  onChange: (box: CropBox) => void
}

/** Khung crop kéo-thả (di chuyển) + kéo góc dưới-phải (đổi kích thước) trên khung
 * preview video — toạ độ tính theo pixel THẬT của video nguồn (`videoWidth`/
 * `videoHeight`), quy đổi sang % để hiển thị đúng dù preview bị scale. */
export function CropBoxSelector({ videoWidth, videoHeight, value, onChange }: CropBoxSelectorProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  function handleMove(e: React.PointerEvent) {
    e.stopPropagation()
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect || rect.width === 0 || videoWidth === 0) return
    const scaleX = videoWidth / rect.width
    const scaleY = videoHeight / rect.height
    const startX = e.clientX
    const startY = e.clientY
    const origin = value

    function onMove(ev: PointerEvent) {
      const dx = (ev.clientX - startX) * scaleX
      const dy = (ev.clientY - startY) * scaleY
      onChange({
        ...origin,
        x: Math.round(Math.max(0, Math.min(videoWidth - origin.width, origin.x + dx))),
        y: Math.round(Math.max(0, Math.min(videoHeight - origin.height, origin.y + dy))),
      })
    }
    function onUp() {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  function handleResize(e: React.PointerEvent) {
    e.stopPropagation()
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect || rect.width === 0 || videoWidth === 0) return
    const scaleX = videoWidth / rect.width
    const scaleY = videoHeight / rect.height
    const startX = e.clientX
    const startY = e.clientY
    const origin = value

    function onMove(ev: PointerEvent) {
      const dx = (ev.clientX - startX) * scaleX
      const dy = (ev.clientY - startY) * scaleY
      onChange({
        ...origin,
        width: Math.round(Math.max(20, Math.min(videoWidth - origin.x, origin.width + dx))),
        height: Math.round(Math.max(20, Math.min(videoHeight - origin.y, origin.height + dy))),
      })
    }
    function onUp() {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  if (videoWidth === 0 || videoHeight === 0) return null

  return (
    <div ref={containerRef} className='pointer-events-none absolute inset-0'>
      <div
        data-testid='crop-box'
        className='pointer-events-auto absolute cursor-move border-2 border-primary bg-primary/10'
        style={{
          left: `${(value.x / videoWidth) * 100}%`,
          top: `${(value.y / videoHeight) * 100}%`,
          width: `${(value.width / videoWidth) * 100}%`,
          height: `${(value.height / videoHeight) * 100}%`,
        }}
        onPointerDown={handleMove}
      >
        <div
          data-testid='crop-box-resize'
          className='absolute -right-1.5 -bottom-1.5 size-3 cursor-nwse-resize rounded-full border border-background bg-primary'
          onPointerDown={handleResize}
        />
      </div>
    </div>
  )
}
