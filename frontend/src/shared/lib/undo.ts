import { useCallback, useEffect, useRef } from 'react'
import { toast } from 'sonner'

/**
 * U41's undo affordance, and the keyboard half of it that accessibility-behaviour.md
 * requires.
 *
 * **Why a hook and not just `toast(...)` at each call site.**  U41's 5-second undo replaces
 * confirmation modals for Confirm and Reject.  accessibility-behaviour.md records the
 * collision that creates, and it is real rather than theoretical: a toast a sighted user can
 * click within 5 seconds may be functionally unreachable for a screen-reader user, who has
 * to first hear it announced and then navigate to it inside the same 5 seconds.
 *
 * The resolution is that **the undo affordance is not toast-only**.  The same window is also
 * available as `Cmd/Ctrl+Z`, firing regardless of where focus currently is, for the specific
 * action just taken.  This does not extend the window -- it adds a second, always-available
 * path to the same window.  The toast stays the visible/discoverable form.
 *
 * **The mechanism that matters** (components.md section 9): the database write happens
 * immediately, but the driver notification is QUEUED and only dispatched when the window
 * closes.  The irreversible act is the message to a person, not the row update -- so that is
 * what is delayed.  Undo cancels the queued notification silently; the driver never learns
 * it nearly happened.  Callers own that queueing; this hook owns the window and the two
 * paths into it.
 *
 * Multiple undos stack independently, each with its own window -- hence a ref holding the
 * most recent, not a single module-level slot.
 */
export type UndoableAction = {
  /** "Confirmed SHP1014 · Dock D1 13:00" -- past tense, states what happened. */
  message: string
  onUndo: () => void
}

const WINDOW_MS = 5000

export function useUndo() {
  // Most-recent-first stack of still-open windows.  Cmd/Ctrl+Z takes the newest, which is
  // the platform-standard undo semantic and also what "the action just taken" means.
  const openRef = useRef<{ id: string | number; onUndo: () => void }[]>([])

  const fire = useCallback((action: UndoableAction) => {
    const id = toast(action.message, {
      duration: WINDOW_MS,
      action: {
        label: 'Undo',
        onClick: () => {
          action.onUndo()
          openRef.current = openRef.current.filter((e) => e.id !== id)
        },
      },
      onAutoClose: () => {
        openRef.current = openRef.current.filter((e) => e.id !== id)
      },
    })
    openRef.current = [{ id, onUndo: action.onUndo }, ...openRef.current]
    return id
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== 'z' || !(e.metaKey || e.ctrlKey) || e.shiftKey) return
      // Never steal the browser's own undo from a text field -- a planner part-way through a
      // rejection note pressing Cmd+Z means "undo my typing", not "undo the confirmation".
      const el = document.activeElement
      const inText =
        el instanceof HTMLInputElement ||
        el instanceof HTMLTextAreaElement ||
        (el instanceof HTMLElement && el.isContentEditable)
      if (inText) return

      const next = openRef.current[0]
      if (!next) return
      e.preventDefault()
      next.onUndo()
      toast.dismiss(next.id)
      openRef.current = openRef.current.slice(1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return { fire }
}
