import type { ReactNode } from 'react'

/** A thin bar for a 0-1 value (the unfilled part is a light step of the same blue). */
export function Meter({ value, label, big = false }: { value: number; label: string; big?: boolean }) {
  const width = `${Math.min(1, Math.max(0, value)) * 100}%`
  return (
    <div
      className={`meter${big ? ' big' : ''}`}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value * 100)}
    >
      <span style={{ width }} />
    </div>
  )
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="stat">
      <span className="value">{value}</span>
      <span className="label">{label}</span>
    </div>
  )
}

export function ErrorNotice({ error, title = 'Something went wrong' }: { error: Error; title?: string }) {
  return (
    <div className="callout error" role="alert">
      <div>
        <strong>{title}</strong>
        <p>{error.message}</p>
      </div>
    </div>
  )
}

export function Note({ children }: { children: ReactNode }) {
  return <div className="callout note">{children}</div>
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <p className="empty" role="status">
      {label}…
    </p>
  )
}
