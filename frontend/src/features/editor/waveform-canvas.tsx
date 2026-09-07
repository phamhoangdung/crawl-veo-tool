import { useEffect, useRef } from 'react'

interface WaveformCanvasProps {
  peaks: number[]
  width: number
  height?: number
  color?: string
}

export function WaveformCanvas({ peaks, width, height = 36, color = '#ffffff' }: WaveformCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx || peaks.length === 0) return

    const dpr = window.devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = height * dpr
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, width, height)
    ctx.fillStyle = color

    const barWidth = width / peaks.length
    const midY = height / 2
    peaks.forEach((peak, i) => {
      const barHeight = Math.max(1, peak * height)
      ctx.fillRect(i * barWidth, midY - barHeight / 2, Math.max(1, barWidth - 1), barHeight)
    })
  }, [peaks, width, height, color])

  return (
    <canvas
      ref={canvasRef}
      data-testid='waveform-canvas'
      style={{ width, height }}
      className='pointer-events-none absolute inset-0 opacity-70'
    />
  )
}
