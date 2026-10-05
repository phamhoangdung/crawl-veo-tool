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

/** While typing in an input field, shortcuts must yield to the typing. */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable
}

/**
 * Familiar video-editor style shortcuts. Only active when `enabled` — the editor
 * lives in a tab and should not capture keys while the user is on another tab.
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
          // Shift to jump further — frame-by-frame fine tuning vs fast scrubbing.
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
