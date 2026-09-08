import { useEffect } from 'react'

export interface EditorShortcutHandlers {
  onTogglePlay: () => void
  onSplit: () => void
  onDelete: () => void
  onDuplicate: () => void
  onUndo: () => void
  onRedo: () => void
  onNudge: (deltaSeconds: number) => void
}

/** Đang gõ trong ô nhập thì phím tắt phải nhường cho việc gõ. */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable
}

/**
 * Phím tắt kiểu editor video quen thuộc. Chỉ hoạt động khi `enabled` — editor
 * nằm trong tab, không nên bắt phím khi người dùng đang ở tab khác.
 */
export function useEditorShortcuts(handlers: EditorShortcutHandlers, enabled = true) {
  useEffect(() => {
    if (!enabled) return

    function onKeyDown(e: KeyboardEvent) {
      if (isTypingTarget(e.target)) return

      const mod = e.metaKey || e.ctrlKey

      if (mod && e.key.toLowerCase() === 'z') {
        e.preventDefault()
        if (e.shiftKey) handlers.onRedo()
        else handlers.onUndo()
        return
      }
      if (mod && e.key.toLowerCase() === 'd') {
        e.preventDefault()
        handlers.onDuplicate()
        return
      }
      if (mod) return

      switch (e.key) {
        case ' ':
          e.preventDefault()
          handlers.onTogglePlay()
          break
        case 's':
        case 'S':
          e.preventDefault()
          handlers.onSplit()
          break
        case 'Delete':
        case 'Backspace':
          e.preventDefault()
          handlers.onDelete()
          break
        case 'ArrowLeft':
          e.preventDefault()
          // Shift để nhảy xa hơn — tinh chỉnh từng frame vs lướt nhanh.
          handlers.onNudge(e.shiftKey ? -5 : -1 / 30)
          break
        case 'ArrowRight':
          e.preventDefault()
          handlers.onNudge(e.shiftKey ? 5 : 1 / 30)
          break
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [enabled, handlers])
}
