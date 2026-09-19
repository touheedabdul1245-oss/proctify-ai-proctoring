// Shared status/empty/error UI. Consolidates duplicated risk-pill markup that
// used to live in four places. Class names stay compatible with monitorUtils
// (risk-pill risk-<level>) so the tested helper contract is unchanged.
import { normalizeLevel } from '../pages/teacher/monitorUtils'

const LEVEL_LABELS = {
  NORMAL: 'Normal',
  ATTENTION: 'Attention',
  ELEVATED: 'Elevated',
  HIGH: 'High Risk',
}

export function RiskPill({ level, compact }) {
  const lv = normalizeLevel(level)
  return (
    <span className={`risk-pill risk-${lv.toLowerCase()}${compact ? ' compact' : ''}`}>
      {LEVEL_LABELS[lv] || lv}
    </span>
  )
}

export function StatusPill({ status, className = 'mon-status' }) {
  const s = String(status || 'IDLE').toUpperCase()
  return <span className={`${className} ${className}-${s.toLowerCase()}`}>{s}</span>
}

export function EmptyState({ title, hint, action }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon" aria-hidden="true">
        ◉
      </div>
      <div className="empty-state-title">{title || 'Nothing here yet'}</div>
      {hint && <div className="empty-state-hint">{hint}</div>}
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  const msg = typeof error === 'string' ? error : error?.message || 'Something went wrong'
  return (
    <div className="error-state" role="alert">
      <div className="error-state-icon" aria-hidden="true">!</div>
      <div className="error-state-title">Could not load this data</div>
      <div className="error-state-hint">{msg}</div>
      {onRetry && (
        <button className="btn btn-secondary btn-sm" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function LoadingState({ label }) {
  return (
    <div className="loading-state">
      <div className="loading-state-spinner" aria-hidden="true" />
      <div className="loading-state-label">{label || 'Loading…'}</div>
    </div>
  )
}