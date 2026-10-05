export interface StudioSettings {
  imageModel: string
  videoModel: string
  /** Number of variants per image generation. Video always generates 1 (about 50-100 times the cost of an image). */
  variantCount: number
  /** File name prefix by episode/project, e.g. "EP001" → EP001_001.png. */
  outputPrefix: string
}

export const IMAGE_MODELS = [
  { id: 'nano-banana', label: 'Nano Banana', pricePerImage: 0.01 },
  { id: 'flux-schnell', label: 'Flux Schnell (rẻ nhất)', pricePerImage: 0.003 },
  { id: 'flux-dev', label: 'Flux Dev (chất hơn)', pricePerImage: 0.025 },
]

export const VIDEO_MODELS = [
  { id: 'luma-ray2', label: 'Luma Ray 2', pricePerSecond: 0.04 },
  { id: 'kling-3.0', label: 'Kling 3.0 (giữ nhân vật tốt)', pricePerSecond: 0.1 },
  { id: 'veo-3.1', label: 'Veo 3.1 (có audio, đắt nhất)', pricePerSecond: 0.4 },
]

export const KEN_BURNS_MOTIONS = [
  { id: 'zoom_in', label: 'Phóng vào chậm' },
  { id: 'zoom_out', label: 'Thu ra chậm' },
  { id: 'pan_right', label: 'Lia ngang' },
]

export const VIDEO_DURATIONS = [4, 5, 8, 10]
