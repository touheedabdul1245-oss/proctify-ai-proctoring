import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api'
import { PageHeader, Card, Badge, Loading, ErrorBox, Field, fmtDate } from '../../components/Ui'
import {
  filterMonitorRows,
  summarize,
  riskClass,
  monitorStatusClass,
  reviewStatusClass,
  REVIEW_ACTIONS,
  formatIndex,
  timeAgo,
  riskHistoryBars,
  shortToken,
  eventLabel,
} from './monitorUtils'

const POLL_MS = 5000
const RISK_FILTERS = ['ALL', 'NORMAL', 'ATTENTION', 'ELEVATED', 'HIGH']
const STATUS_FILTERS = ['ALL', 'LIVE', 'ACTIVE', 'IDLE']

function usePolling(fn, deps = [], interval = POLL_MS) {
  const [state, setState] = useState({ data: null, loading: true, error: null })
  const fnRef = useRef(fn)
  fnRef.current = fn
  const run = useCallback(async (silent) => {
    if (!silent) setState((s) => ({ ...s, loading: true }))
    try {
      const data = await fnRef.current()
      setState({ data, loading: false, error: null })
    } catch (err) {
      setState((s) => ({ ...s, loading: false, error: err }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => {
    run(false)
    const t = setInterval(() => run(true), interval)
    return () => clearInterval(t)
  }, [run, interval])
  return { ...state, refresh: () => run(true) }
}

function RiskPill({ level }) {
  return <span className={riskClass(level)}>{normalizeLevel(level)}</span>
}

function normalizeLevel(level) {
  const lv = String(level || 'NORMAL').toUpperCase()
  return lv === 'LOW' ? 'NORMAL' : lv
}

function EvidenceThumb({ ev }) {
  const isImage = String(ev.evidence_type || '').toLowerCase().includes('image')
  const loadable =
    isImage &&
    (ev.media_url?.startsWith('data:') ||
      ev.media_url?.startsWith('http://') ||
      ev.media_url?.startsWith('https://') ||
      ev.media_url?.startsWith('/api/evidence/'))
  return (
    <div className="evidence-card">
      {loadable ? (
        <div className="evidence-img">
          <img src={ev.media_url} alt={ev.description || 'evidence'} />
        </div>
      ) : (
        <div className="evidence-thumb">{isImage ? 'IMG' : 'AUD'} </div>
      )}
      <div className="evidence-meta">
        <div className="evidence-type">{ev.evidence_type}</div>
        <div className="evidence-desc">{ev.description || '—'}</div>
        <div className="evidence-path muted">{ev.source ? `${ev.source} · ` : ''}{fmtDate(ev.captured_at)}</div>
      </div>
    </div>
  )
}

function IncidentReview({ incident, onReview }) {
  const [remarks, setRemarks] = useState('')
  const [busy, setBusy] = useState(false)
  const pending = (incident.review_status || 'PENDING').toUpperCase() === 'PENDING'
  const confirmed = (incident.review_status || '').toUpperCase() === 'CONFIRMED'

  return (
    <div className="incident-card">
      <div className="incident-head">
        <span className="incident-type">{incident.incident_type}</span>
        <RiskPill level={incident.risk_level} />
        <span className={reviewStatusClass(incident.review_status)}>{incident.review_status}</span>
        {incident.resolved ? <Badge status="completed" /> : !!pending && <Badge status="pending" />}
      </div>
      <div className="incident-desc">{incident.description}</div>
      <div className="incident-meta muted">
        {incident.event_count} event(s) · confidence {(incident.confidence ?? 0).toFixed(2)}
        {incident.first_event_at ? ` · first ${fmtDate(incident.first_event_at)}` : ''}
        {incident.last_event_at ? ` · last ${fmtDate(incident.last_event_at)}` : ''}
      </div>
      {incident.evidence?.length > 0 && (
        <div className="evidence-row">
          {incident.evidence.map((ev) => <EvidenceThumb key={ev.id} ev={ev} />)}
        </div>
      )}
      {incident.review_notes && (
        <div className="review-notes">Teacher: {incident.review_notes}</div>
      )}
      {(pending || confirmed) && (
        <div className="review-panel">
          <Field label="Teacher remarks">
            <textarea
              className="input"
              rows={2}
              placeholder="Notes / reason for this review…"
              value={remarks}
              onChange={(e) => setRemarks(e.target.value)}
            />
          </Field>
          <div className="review-actions">
            {pending && (
              <>
                <button
                  className="btn btn-primary btn-sm"
                  disabled={busy}
                  onClick={async () => { setBusy(true); await onReview(incident.id, 'CONFIRM', remarks); setBusy(false); setRemarks('') }}
                >
                  Confirm incident
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={busy}
                  onClick={async () => { setBusy(true); await onReview(incident.id, 'DISMISS', remarks); setBusy(false); setRemarks('') }}
                >
                  Dismiss
                </button>
              </>
            )}
            {confirmed && (
              <button
                className="btn btn-secondary btn-sm"
                disabled={busy}
                onClick={async () => { setBusy(true); await onReview(incident.id, 'RESOLVE', remarks); setBusy(false); setRemarks('') }}
              >
                Mark resolved
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function RiskHistory({ riskRows }) {
  const bars = riskHistoryBars(riskRows)
  if (!bars.length) return <div className="empty">No risk snapshots yet.</div>
  const peak = Math.max(1, ...bars.map((b) => b.value))
  return (
    <div>
      <div className="risk-bars">
        {bars.map((b, i) => (
          <div key={i} className="risk-bar">
            <div
              className={`risk-bar-fill fill-${b.level.toLowerCase()}`}
              style={{ height: `${Math.round((b.value / peak) * 100)}%` }}
              title={`${b.level} ${formatIndex(b.value)}`}
            />
          </div>
        ))}
      </div>
      <div className="risk-bars-legend muted">
        {bars.slice(-6).map((b, i) => (
          <span key={i} className="risk-bars-legend-item">
            <i className={`dot risk-${b.level.toLowerCase()}`} /> {b.at ? timeAgo(b.at) : 'n/a'}
          </span>
        ))}
      </div>
    </div>
  )
}

function SessionDetail({ detail, onReview }) {
  if (!detail) return null
  return (
    <div className="session-detail">
      <div className="detail-hero">
        <div>
          <h2>{detail.student_name}</h2>
          <div className="detail-student-line muted">{detail.student_email}</div>
          <div className="detail-session-line muted">
            {detail.exam_title} ({detail.exam_code}) · {shortToken(detail.session_token, 16)}
          </div>
        </div>
        <div className="detail-hero-right">
          <RiskPill level={detail.risk_level} />
          <span className={monitorStatusClass(detail.monitor_status)}>{detail.monitor_status}</span>
          <Badge status={detail.status} />
        </div>
      </div>
      <div className="detail-stats">
        <div className="stat-chips">
          <span className="chip">Risk index <strong>{formatIndex(detail.risk_index)}</strong></span>
          <span className="chip">Pending <strong>{detail.pending_incidents}</strong></span>
          <span className="chip">Incidents <strong>{detail.incidents?.length || 0}</strong></span>
          <span className="chip">Evidence <strong>{detail.evidence?.length || 0}</strong></span>
          <span className="chip">Cam <strong>{detail.camera_available ? 'ON' : 'OFF'}</strong></span>
          <span className="chip">Mic <strong>{detail.audio_available ? 'ON' : 'OFF'}</strong></span>
          <span className="chip">Active <strong>{detail.last_activity_at ? timeAgo(detail.last_activity_at) : '—'}</strong></span>
        </div>
      </div>

      <div className="detail-grid">
        <Card title={`Risk history (${detail.risk_rows?.length || 0})`}>
          <RiskHistory riskRows={detail.risk_rows} />
        </Card>
        <Card title={`Recent AI events (${detail.events?.length || 0})`}>
          {detail.events?.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Source</th>
                  <th>Severity</th>
                  <th>Conf</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {detail.events.slice(0, 10).map((e) => (
                  <tr key={e.id}>
                    <td>{eventLabel(e)}</td>
                    <td>{e.source || '—'}</td>
                    <td><Badge status={e.severity || 'info'} /></td>
                    <td>{(e.confidence ?? 0).toFixed(2)}</td>
                    <td>{timeAgo(e.occurred_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty">No AI events yet.</div>
          )}
        </Card>
      </div>

      <Card title={`Incident timeline (${detail.incidents?.length || 0})`}>
        {detail.incidents?.length ? (
          detail.incidents.map((inc) => (
            <IncidentReview key={inc.id} incident={inc} onReview={onReview} />
          ))
        ) : (
          <div className="empty">No incidents for this session.</div>
        )}
      </Card>

      {detail.evidence?.length > 0 && (
        <Card title={`Evidence (${detail.evidence.length})`}>
          <div className="evidence-row">
            {detail.evidence.map((ev) => <EvidenceThumb key={ev.id} ev={ev} />)}
          </div>
        </Card>
      )}
    </div>
  )
}

export default function Monitor() {
  const [q, setQ] = useState('')
  const [riskFilter, setRiskFilter] = useState('ALL')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [selectedId, setSelectedId] = useState(null)
  const [notify, setNotify] = useState('')

  const overview = usePolling(() => api('/proctoring/monitor/overview'), [])
  const detail = usePolling(
    () => (selectedId ? api(`/proctoring/monitor/sessions/${selectedId}`) : Promise.resolve(null)),
    [selectedId],
    4000,
  )

  const rows = useMemo(() => overview.data?.sessions || [], [overview.data])
  const filtered = useMemo(
    () => filterMonitorRows(rows, { q, risk: riskFilter, status: statusFilter }),
    [rows, q, riskFilter, statusFilter],
  )
  const stats = useMemo(() => summarize(rows), [rows])

  async function reviewIncident(incidentId, action, remarks) {
    const out = await api('/proctoring/monitor/review', {
      method: 'POST',
      body: { incident_id: incidentId, action, remarks },
    })
    setNotify(`${out.message}`)
    window.setTimeout(() => setNotify(''), 4000)
    overview.refresh()
    detail.refresh()
  }

  return (
    <div>
      <PageHeader
        title="Live Monitor"
        subtitle="Teacher monitoring dashboard — AI observations are signals, the teacher review is the final decision."
        actions={<button className="btn btn-secondary btn-sm" onClick={() => { overview.refresh(); detail.refresh() }}>Refresh</button>}
      />

      {notify && <div className="success-box">{notify}</div>}

      {overview.loading && !overview.data ? (
        <Loading />
      ) : (
        <>
          <Card className="mon-stats">
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-value">{stats.total}</div>
                <div className="stat-label">Active sessions</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{stats.live}</div>
                <div className="stat-label">Live signals</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{stats.pending}</div>
                <div className="stat-label">Pending reviews</div>
              </div>
              {(['ATTENTION', 'ELEVATED', 'HIGH']).map((lv) => (
                <div key={lv} className="stat-card">
                  <div className="stat-value">
                    <span className={riskClass(lv)}>{stats.byRisk[lv] ?? 0}</span>
                  </div>
                  <div className="stat-label">{lv} students</div>
                </div>
              ))}
            </div>
          </Card>

          <Card title="Students">
            <div className="mon-toolbar">
              <input
                className="input mon-search"
                placeholder="Search name, email, exam, session…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
              <select className="input" value={riskFilter} onChange={(e) => setRiskFilter(e.target.value)}>
                {RISK_FILTERS.map((f) => (
                  <option key={f} value={f}>{f === 'ALL' ? 'All risk levels' : f}</option>
                ))}
              </select>
              <select className="input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                {STATUS_FILTERS.map((f) => (
                  <option key={f} value={f}>{f === 'ALL' ? 'All monitoring states' : f}</option>
                ))}
              </select>
              <span className="muted mon-count">{filtered.length} of {rows.length} shown</span>
            </div>

            {overview.error && <ErrorBox error={overview.error} />}
            {filtered.length ? (
              <div className="mon-grid">
                {filtered.map((r) => (
                  <button key={r.id} className="mon-card" onClick={() => setSelectedId(r.id)}>
                    <div className="mon-card-top">
                      <span className="mon-name">{r.student_name}</span>
                      <span className={monitorStatusClass(r.monitor_status)}>{r.monitor_status}</span>
                    </div>
                    <div className="mon-card-sub muted">{r.student_email}</div>
                    <div className="mon-card-mid">
                      <RiskPill level={r.risk_level} />
                      <span className="mon-index muted">idx {formatIndex(r.risk_index)}</span>
                    </div>
                    <div className="mon-card-exam muted">
                      {r.exam_code} · {shortToken(r.session_token)}
                    </div>
                    <div className="mon-card-foot">
                      <span className="mon-tag" title="Pending incidents">{r.pending_incidents} pending</span>
                      <span className="mon-tag" title="Incidents">{r.incident_count} inc</span>
                      <span className="mon-tag" title="Evidence">{r.evidence_count} ev</span>
                      <span className="mon-tag" title="Camera"><b>{r.camera_available ? 'CAM' : 'cam'}</b></span>
                      <span className="mon-tag" title="Microphone"><b>{r.audio_available ? 'MIC' : 'mic'}</b></span>
                    </div>
                    {r.recent_events?.length > 0 && (
                      <div className="mon-events">
                        {r.recent_events.slice(0, 4).map((e) => (
                          <span key={`${r.id}-${e.id}`} className="mon-event">{eventLabel(e)}</span>
                        ))}
                        <span className="muted">last {timeAgo(r.last_activity_at)}</span>
                      </div>
                    )}
                  </button>
                ))}
              </div>
            ) : (
              <div className="empty">No students match the current filters.</div>
            )}
          </Card>
        </>
      )}

      {selectedId && (
        <div className="modal-backdrop" onClick={() => setSelectedId(null)}>
          <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h3>Student monitor details</h3>
              <button className="btn btn-ghost" onClick={() => setSelectedId(null)}>×</button>
            </div>
            <div className="modal-body">
              {detail.error && <ErrorBox error={detail.error} />}
              {detail.data ? (
                <SessionDetail detail={detail.data} onReview={reviewIncident} />
              ) : (
                <Loading />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}