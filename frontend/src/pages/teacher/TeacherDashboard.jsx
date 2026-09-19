import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api'
import { Card, PageHeader, StatCard, Badge } from '../../components/Ui'
import AnimatedCounter from '../../components/AnimatedCounter'
import TrustGauge from '../../components/TrustGauge'
import { RiskPill, StatusPill, EmptyState, ErrorState, LoadingState } from '../../components/Status'
import { countRisk, eventLabel, timeAgo, filterMonitorRows, MONITOR_LEVELS } from './monitorUtils'

function usePoll(fn, interval, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null })
  const [tick, setTick] = useState(0)
  function refresh() { setTick((t) => t + 1) }
  useEffect(() => {
    let alive = true
    setState({ data: state.data, loading: state.data === null, error: null })
    fn()
      .then((data) => alive && setState({ data, loading: false, error: null }))
      .catch((err) => alive && setState((s) => ({ ...s, loading: false, error: err })))
    const t = interval ? setInterval(() => {
      fn()
        .then((data) => alive && setState({ data, loading: false, error: null }))
        .catch(() => {})
    }, interval) : null
    return () => {
      alive = false
      if (t) clearInterval(t)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  return { ...state, refresh }
}

const RISK_FILL = { NORMAL: 'fill-normal', ATTENTION: 'fill-attention', ELEVATED: 'fill-elevated', HIGH: 'fill-high' }

const SESSION_LABELS = {
  NOT_STARTED: 'Not started',
  PREPARING: 'Preparing',
  ACTIVE: 'In progress',
  SUBMITTED: 'Submitted',
  EXPIRED: 'Expired',
  TERMINATED: 'Terminated',
}

export default function TeacherDashboard() {
  const navigate = useNavigate()
  const stats = usePoll(() => api('/dashboard/stats'), 0)
  const live = usePoll(() => api('/proctoring/monitor/live-students'), 15000)
  const analytics = usePoll(() => api('/analytics/overview'), 0)

  const [query, setQuery] = useState('')

  const counts = stats.data?.counts || {}
  const ldata = live.data || {}
  const rows = live.data?.rows || []
  const filtered = filterMonitorRows(rows, { q: query })
  const byRisk = countRisk(rows)
  const totals = analytics.data?.totals || {}
  const incidentSummary = analytics.data?.incident_summary || {}
  const recent = analytics.data?.recent_activity || []
  const hasIncidents = Object.keys(incidentSummary).length > 0

  const riskMax = Math.max(1, ...MONITOR_LEVELS.map((lv) => byRisk[lv] || 0))
  const incidentTotal = Object.values(incidentSummary).reduce((a, b) => a + Number(b) || 0, 0)

  return (
    <div>
      <PageHeader
        title="Command Center"
        subtitle="Live examination & integrity overview — states always come from the server clock, never the browser."
        actions={
          <>
            <button className="btn btn-secondary" onClick={() => navigate('/teacher/monitor')}>
              Live Monitor
            </button>
            <button className="btn btn-primary" onClick={() => navigate('/teacher/exams/new')}>
              + Create exam
            </button>
          </>
        }
      />

      <div className="stats-grid">
        <StatCard accent="brand" label="Exams" value={<AnimatedCounter value={counts.total_exams ?? 0} />} />
        <StatCard label="Questions" value={<AnimatedCounter value={counts.questions ?? 0} />} />
        <StatCard accent="ok" label="Students Enrolled" value={<AnimatedCounter value={counts.students ?? 0} />} />
        <StatCard accent="ok" label="Published Results" value={<AnimatedCounter value={totals.published_results ?? 0} />} />
        <StatCard accent="warn" label="Pending Incidents" value={<AnimatedCounter value={ldata.pending_incidents ?? totals.pending_incidents ?? 0} />} />
        <StatCard accent="danger" label="Elevated / High Risk" value={<AnimatedCounter value={ldata.elevated_risk ?? 0} />} />
      </div>

      <Card title="Live student list">
        {live.loading && !live.data ? (
          <LoadingState label="Loading live students…" />
        ) : live.error ? (
          <ErrorState error={live.error} onRetry={live.refresh} />
        ) : rows.length === 0 && ldata.students === 0 ? (
          <EmptyState
            title="No assigned students yet"
            hint="Create an exam, add questions, then assign students or batches. Their live state appears here in real time."
            action={
              <button className="btn btn-secondary btn-sm" onClick={() => navigate('/teacher/exams/new')}>
                Create exam
              </button>
            }
          />
        ) : (
          <>
            <div className="live-summary">
              <span className="chip">Exams <strong>{ldata.exams ?? 0}</strong></span>
              <span className="chip">Students <strong>{ldata.students ?? 0}</strong></span>
              <span className="chip live-chip">Live <strong>{ldata.live_count ?? 0}</strong></span>
              <span className="chip">In progress <strong>{ldata.in_progress_count ?? 0}</strong></span>
              <span className="chip">Preparing <strong>{ldata.preparing_count ?? 0}</strong></span>
              <span className="chip">Not started <strong>{ldata.not_started_count ?? 0}</strong></span>
              <span className="chip">Submitted <strong>{ldata.submitted_count ?? 0}</strong></span>
              <span className="chip">Expired <strong>{ldata.expired_count ?? 0}</strong></span>
              <span className="chip">Terminated <strong>{ldata.terminated_count ?? 0}</strong></span>
            </div>

            <div className="mon-toolbar">
              <input
                className="input mon-search"
                placeholder="Search student, email, exam, code…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <span className="muted mon-count">{filtered.length} of {rows.length} shown</span>
            </div>

            <div className="table-wrap">
              <table className="table live-table">
                <thead>
                  <tr>
                    <th>Student</th>
                    <th>Exam</th>
                    <th>Status</th>
                    <th>Monitor</th>
                    <th>Trust / Risk</th>
                    <th>Cam</th>
                    <th>Mic</th>
                    <th>Pending</th>
                    <th>Inc · Ev</th>
                    <th>Events·24h</th>
                    <th>Last activity</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((r) => (
                    <tr key={`${r.exam_id}-${r.student_db_id}`} className="row-click" onClick={() => navigate('/teacher/monitor')}>
                      <td>
                        <div className="live-cell-name">{r.student_name}</div>
                        <div className="live-cell-sub">
                          <span className="mono">{r.student_id || '—'}</span> · {r.student_email}
                        </div>
                      </td>
                      <td>
                        <div className="live-cell-name">{r.exam_title}</div>
                        <div className="live-cell-sub">
                          <span className="mono">{r.exam_code}</span> · <Badge status={r.exam_status} />
                        </div>
                      </td>
                      <td>
                        <span className={`session-status session-${r.status.toLowerCase()}`}>
                          {SESSION_LABELS[r.status] || r.status}
                        </span>
                      </td>
                      <td>
                        <StatusPill status={r.monitor_status} />
                        {r.latest_event && <div className="live-cell-sub">{eventLabel({ event_type: r.latest_event })}</div>}
                      </td>
                      <td>
                        <div className="live-trust-row">
                          {r.trust_score != null ? (
                            <TrustGauge size={38} score={r.trust_score} level={r.trust_level} showLabel={false} />
                          ) : (
                            <span className="live-cell-sub">—</span>
                          )}
                          <RiskPill level={r.risk_level} compact />
                        </div>
                      </td>
                      <td>{r.camera ? <span className="mon-tag ok-text">ON</span> : <span className="mon-tag">off</span>}</td>
                      <td>{r.microphone ? <span className="mon-tag ok-text">ON</span> : <span className="mon-tag">off</span>}</td>
                      <td>{r.pending_incidents || 0}</td>
                      <td>{r.incident_count || 0} · {r.evidence_count || 0}</td>
                      <td>{r.event_count_24h || 0}</td>
                      <td className="mono muted">{r.last_activity_at ? timeAgo(r.last_activity_at) : '—'}</td>
                    </tr>
                  ))}
                  {!filtered.length && (
                    <tr>
                      <td colSpan={11} className="empty">No students match the current search.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Card>

      <div className="panel-grid">
        <Card title="Risk distribution · assigned students">
          {live.loading && !live.data ? (
            <LoadingState label="Loading distribution…" />
          ) : live.error ? (
            <ErrorState error={live.error} onRetry={live.refresh} />
          ) : rows.length === 0 ? (
            <EmptyState title="No students yet" />
          ) : (
            <>
              <div className="risk-bars">
                {MONITOR_LEVELS.map((lv) => (
                  <div key={lv} className="risk-bar">
                    <div
                      className={`risk-bar-fill ${RISK_FILL[lv]}`}
                      style={{ height: `${((byRisk[lv] || 0) / riskMax) * 100}%` }}
                      title={`${byRisk[lv] || 0}`}
                    />
                  </div>
                ))}
              </div>
              <div className="risk-bars-legend">
                {MONITOR_LEVELS.map((lv) => (
                  <span key={lv} className="risk-bars-legend-item">
                    <RiskPill level={lv} compact /> {byRisk[lv] || 0}
                  </span>
                ))}
              </div>
            </>
          )}
        </Card>

        <Card title="Incident review queue">
          {analytics.loading ? (
            <LoadingState label="Loading incidents…" />
          ) : analytics.error ? (
            <ErrorState error={analytics.error} onRetry={analytics.refresh} />
          ) : !hasIncidents ? (
            <EmptyState
              title="All clear"
              hint="No reviewed incidents to display yet. Confirmed, dismissed and resolved incidents surface here."
            />
          ) : (
            <>
              {[['PENDING', 'warn'], ['CONFIRMED', 'danger'], ['DISMISSED', 'ok']].map(([key, meter]) => {
                const n = Number(incidentSummary[key] || 0)
                return (
                  <div key={key} className="incident-q-row">
                    <span className="chip">{key}</span>
                    <span className="bar-meter">
                      <i className={`${meter}`} style={{ width: `${(n / Math.max(1, incidentTotal)) * 100}%` }} />
                    </span>
                    <span className="incident-q-count">{n}</span>
                  </div>
                )
              })}
              <div className="segment-row" style={{ marginTop: 12 }}>
                <button className="btn btn-secondary btn-sm" onClick={() => navigate('/teacher/analytics')}>
                  Open analytics
                </button>
              </div>
            </>
          )}
        </Card>
      </div>

      <Card title="Recent platform activity">
        <AnalyticsActivity analytics={analytics} />
      </Card>
    </div>
  )
}

function AnalyticsActivity({ analytics }) {
  if (analytics.loading) return <LoadingState label="Loading activity…" />
  if (analytics.error) return <ErrorState error={analytics.error} onRetry={analytics.refresh} />
  const list = analytics.data?.recent_activity || []
  if (!list.length) return <EmptyState title="No activity yet" hint="Examination, enrolment and review actions will be logged here." />
  return (
    <div className="feed">
      {list.map((a, i) => (
        <div key={i} className="feed-item">
          <span className={`feed-dot ${String(a.action || '').includes('confirm') ? 'danger' : String(a.action || '').includes('dismiss') ? 'attention' : ''}`} />
          <div className="feed-body">
            <div className="feed-action">{a.action}</div>
            <div className="feed-meta">
              {a.actor_email || 'system'} · {timeAgo(a.created_at)}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}