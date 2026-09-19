// Stage-4 monitor page: pure helpers (no React, no browser globals) so they stay
// unit-testable with `node --test` across the same wire contract the backend emits.

export const RISK_ORDER = { NORMAL: 0, LOW: 1, ATTENTION: 2, ELEVATED: 3, HIGH: 4 }

export const MONITOR_LEVELS = ['NORMAL', 'ATTENTION', 'ELEVATED', 'HIGH']

export const MONITOR_STATUS_ORDER = { IDLE: 0, ACTIVE: 1, LIVE: 2, DONE: 3 }

export function normalizeLevel(level) {
  const up = String(level || 'NORMAL').toUpperCase()
  return up in RISK_ORDER ? up : 'NORMAL'
}

export function normalizeStatus(status) {
  const up = String(status || 'IDLE').toUpperCase()
  return up in MONITOR_STATUS_ORDER ? up : 'IDLE'
}

export function riskClass(level) {
  return `risk-pill risk-${normalizeLevel(level).toLowerCase()}`
}

export function monitorStatusClass(status) {
  return `mon-status mon-${normalizeStatus(status).toLowerCase()}`
}

export function reviewStatusClass(status) {
  return `badge badge-review-${String(status || 'PENDING').toLowerCase()}`
}

export function filterMonitorRows(rows, { q = '', risk = 'ALL', status = 'ALL' } = {}) {
  const needle = String(q || '')
    .trim()
    .toLowerCase()
  const riskUp = String(risk || 'ALL').toUpperCase()
  const statusUp = String(status || 'ALL').toUpperCase()
  const list = Array.isArray(rows) ? rows : []
  return list.filter((r) => {
    if (riskUp !== 'ALL' && normalizeLevel(r.risk_level) !== riskUp) return false
    if (statusUp !== 'ALL' && normalizeStatus(r.monitor_status) !== statusUp) return false
    if (!needle) return true
    const hay = [
      r.student_name,
      r.student_email,
      r.exam_code,
      r.exam_title,
      r.session_token,
      String(r.student_id ?? ''),
    ]
      .join(' ')
      .toLowerCase()
    return hay.includes(needle)
  })
}

export function summarize(rows) {
  const list = Array.isArray(rows) ? rows : []
  return {
    total: list.length,
    live: list.filter((r) => normalizeStatus(r.monitor_status) === 'LIVE').length,
    pending: list.reduce((acc, r) => acc + (Number(r.pending_incidents) || 0), 0),
    byRisk: countRisk(list),
  }
}

export function countRisk(rows) {
  const list = Array.isArray(rows) ? rows : []
  const counts = Object.fromEntries(MONITOR_LEVELS.map((lv) => [lv, 0]))
  for (const r of list) counts[normalizeLevel(r.risk_level)] += 1
  return counts
}

export function timeAgo(iso, now = Date.now()) {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return String(iso)
  const diff = Math.max(0, now - t)
  const sec = Math.floor(diff / 1000)
  if (sec < 10) return 'just now'
  if (sec < 60) return `${sec}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  return `${Math.floor(hr / 24)}d ago`
}

export function riskHistoryBars(riskRows, { max = 8 } = {}) {
  const list = Array.isArray(riskRows) ? riskRows : []
  const sorted = [...list].sort((a, b) => {
    const ta = a.recorded_at ? new Date(a.recorded_at).getTime() : -(a.id || 0)
    const tb = b.recorded_at ? new Date(b.recorded_at).getTime() : -(b.id || 0)
    return ta - tb
  })
  return sorted.slice(-max).map((r) => ({
    level: normalizeLevel(r.level),
    value: Number(r.index_value ?? r.risk_index ?? r.score ?? 0),
    at: r.recorded_at,
  }))
}

export const REVIEW_ACTIONS = {
  CONFIRM: { label: 'Confirm', badge: 'confirmed', next: 'CONFIRMED' },
  DISMISS: { label: 'Dismiss', badge: 'dismissed', next: 'DISMISSED' },
  RESOLVE: { label: 'Resolve', badge: 'resolved', next: 'RESOLVED' },
}

export function formatIndex(value) {
  const n = Number(value)
  if (Number.isNaN(n)) return '—'
  return n.toFixed(3)
}

export function shortToken(token, n = 8) {
  if (!token) return ''
  return String(token).slice(0, n)
}

export function eventLabel(event) {
  return String(event?.event_type || '—').replace(/_/g, ' ').toLowerCase()
}