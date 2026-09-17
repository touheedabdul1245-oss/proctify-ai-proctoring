import { useEffect, useState } from 'react'

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  )
}

export function Card({ title, children, className = '' }) {
  return (
    <div className={`card ${className}`}>
      {title && <div className="card-title">{title}</div>}
      {children}
    </div>
  )
}

export function StatCard({ label, value, accent }) {
  return (
    <div className={`stat-card ${accent ? `accent-${accent}` : ''}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}

export function Badge({ status }) {
  const s = String(status || '').toUpperCase()
  return <span className={`badge badge-${s.toLowerCase()}`}>{s}</span>
}

export function Table({ columns, rows, rowKey = 'id', onRowClick }) {
  if (!rows?.length) {
    return <div className="empty">No records found.</div>
  }
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r[rowKey] ?? i} onClick={onRowClick ? () => onRowClick(r) : undefined}>
              {columns.map((c) => (
                <td key={c.key}>{c.render ? c.render(r) : r[c.key] ?? '—'}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Modal({ open, onClose, title, children, wide }) {
  if (!open) return null
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={`modal ${wide ? 'modal-wide' : ''}`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="btn btn-ghost" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  )
}

export function Field({ label, children, required }) {
  return (
    <label className="field">
      <span className="field-label">
        {label} {required && <em>*</em>}
      </span>
      {children}
    </label>
  )
}

export function Loading() {
  return <div className="page-loading">Loading…</div>
}

export function ErrorBox({ error }) {
  if (!error) return null
  const msg = typeof error === 'string' ? error : error?.message || JSON.stringify(error)
  return <div className="error-box">{msg}</div>
}

export function useAsync(fn, deps) {
  const [state, setState] = useState({ data: null, loading: true, error: null })
  const [tick, setTick] = useState(0)
  function refresh() {
    setTick((t) => t + 1)
  }
  useEffect(() => {
    let alive = true
    setState({ data: null, loading: true, error: null })
    fn()
      .then((data) => alive && setState({ data, loading: false, error: null }))
      .catch((err) => alive && setState({ data: null, loading: false, error: err }))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  return { ...state, refresh }
}

export function fmtDate(dt) {
  if (!dt) return '—'
  const d = new Date(dt)
  if (Number.isNaN(d.getTime())) return String(dt)
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}