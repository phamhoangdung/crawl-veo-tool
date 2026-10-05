export type BootStepId = 'backend' | 'categories' | 'followed'

/**
 * `weight` is the percentage that step contributes when it completes. The backend takes most of it because
 * the packaged build must also start the PyInstaller sidecar (a few seconds → tens of seconds).
 */
export const BOOT_STEPS: { id: BootStepId; label: string; weight: number }[] = [
  { id: 'backend', label: 'Đang khởi động dịch vụ nền...', weight: 60 },
  { id: 'categories', label: 'Đang tải danh sách chuyên mục...', weight: 20 },
  { id: 'followed', label: 'Đang tải lựa chọn của bạn...', weight: 20 },
]

export function bootPercent(done: ReadonlySet<BootStepId>): number {
  return BOOT_STEPS.reduce((sum, s) => sum + (done.has(s.id) ? s.weight : 0), 0)
}
