import { useEffect, useRef, type ReactNode } from 'react'
import { initials } from '../lib/format'
import { RESULT, STATUS } from '../lib/labels'

export function StatusChip({ status }: { status: keyof typeof STATUS }) {
  const s = STATUS[status]
  return <span className={`chip tone-${s.tone}`}><span className="glyph" aria-hidden="true">{s.glyph}</span>{s.label}</span>
}

export function ResultChip({ result, label }: { result: keyof typeof RESULT; label?: string }) {
  const r = RESULT[result]
  return <span className={`chip tone-${r.tone}`}><span className="glyph" aria-hidden="true">{r.glyph}</span>{label ?? r.label}</span>
}

export function Avatar({ name }: { name: string }) {
  return <span className="avatar" aria-hidden="true">{initials(name)}</span>
}

export function SourceChip({ id, onOpen }: { id: string; onOpen?: (id: string) => void }) {
  return (
    <button type="button" className="source-chip" onClick={() => onOpen?.(id)} title={`Open source ${id}`}>
      {id}
    </button>
  )
}

export function Banner({ tone, title, children, actions }: {
  tone: 'warn' | 'error' | 'info' | 'stale'; title: string; children?: ReactNode; actions?: ReactNode
}) {
  return (
    <div className={`banner ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <div><span className="title">{title}</span>{children ? <> {children}</> : null}</div>
      {actions ? <div className="actions">{actions}</div> : null}
    </div>
  )
}

/** Native modal dialog: focus moves inside, Tab stays inside, Escape closes, focus returns on close. */
export function Dialog({ open, onClose, className = 'modal', labelledBy, children }: {
  open: boolean; onClose: () => void; className?: string; labelledBy: string; children: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) {
      el.showModal()
      // React's autoFocus does not reach a dialog that opens after mount; honour data-autofocus instead.
      el.querySelector<HTMLElement>('[data-autofocus]')?.focus()
    }
    if (!open && el.open) el.close()
  }, [open])
  return (
    <dialog ref={ref} className={className} aria-labelledby={labelledBy} onClose={onClose}
      onCancel={(e) => { e.preventDefault(); onClose() }}>
      {open ? children : null}
    </dialog>
  )
}
