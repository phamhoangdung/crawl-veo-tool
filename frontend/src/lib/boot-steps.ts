export type BootStepId = 'backend' | 'categories' | 'followed'

/**
 * `weight` là phần trăm mà bước đó đóng góp khi xong. Backend chiếm phần lớn vì
 * bản đóng gói phải bật cả PyInstaller sidecar (vài giây → hàng chục giây).
 */
export const BOOT_STEPS: { id: BootStepId; label: string; weight: number }[] = [
  { id: 'backend', label: 'Đang khởi động dịch vụ nền...', weight: 60 },
  { id: 'categories', label: 'Đang tải danh sách chuyên mục...', weight: 20 },
  { id: 'followed', label: 'Đang tải lựa chọn của bạn...', weight: 20 },
]

export function bootPercent(done: ReadonlySet<BootStepId>): number {
  return BOOT_STEPS.reduce((sum, s) => sum + (done.has(s.id) ? s.weight : 0), 0)
}
