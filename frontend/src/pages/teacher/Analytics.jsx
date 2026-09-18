import { useMemo, useState } from 'react'
import { api } from '../../api'
import { PageHeader, Card, Badge, Loading, ErrorBox, useAsync, fmtDate } from '../../components/Ui'

function BarRow({ label, value, max, accent }) {
  const pct = max > 0 ? Math.max(4, Math.round((value / max) * 100)) : 0
  return (
    <div className="anal-bar-row">
      <span className="anal-bar-label">{label}</span>
      <div className="anal-bar-track">
        <div className={`anal-bar-fill ${accent || ''}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="anal-bar-value">{value}</span>
    </div>
  )
}

export default function Analytics() {
  const [examId, setExamId] = useState('')
  const [drill, setDrill] = useState(null)
  const overview = useAsync(() => api('/analytics/overview'), [])
  const exams = useAsync(() => api('/exams'), [])
  const [error, setError] = useState(null)

  const ov = overview.data || {}
  const totals = ov.totals || {}
  const results = ov.results || {}
  const riskDist = ov.risk_distribution || {}
  const incident = ov.incident_summary || {}
  const activity = ov.recent_activity || []

  async function loadDrill(id) {
    setError(null)
    setDrill(null)
    if (!id) return
    try {
      const d = await api(`/analytics/exams/${id}`)
      setDrill(d)
    } catch (e) {
      setError(e?.message || 'Could not load exam analytics')
    }
  }

  const maxRisk = useMemo(() => Math.max(1, ...Object.values(riskDist)), [riskDist])
  const maxDist = useMemo(() => (drill ? Math.max(1, ...drill.score_distribution.map((b) => b.count || 0)) : 1), [drill])
  const maxTrend = useMemo(() => (drill ? Math.max(1, ...drill.event_trend.map((b) => b.count || 0)) : 1), [drill])
  const maxDiff = useMemo(
    () => (drill ? Math.max(1, ...drill.question_difficulty.map((q) => q.facility ?? 0)) : 1),
    [drill],
  )

  const statCards = [
    { label: 'Exams', value: totals.exams },
    { label: 'Students', value: totals.students },
    { label: 'Sessions', value: totals.sessions },
    { label: 'Results', value: totals.results },
    { label: 'Published', value: results.published_count },
    { label: 'Unpublished', value: results.unpublished_count },
  ]

  return (
    <div>
      <PageHeader
        title="Analytics"
        subtitle="Aggregate insights across exams, results and proctoring signals."
        actions={
          <div className="segment-row">
            <select
              className="input"
              value={examId}
              onChange={(e) => {
                setExamId(e.target.value)
                loadDrill(e.target.value)
              }}
            >
              <option value="">Select an exam to drill down…</option>
              {exams.data?.map((e) => (
                <option key={e.id} value={e.id}>{e.title}</option>
              ))}
            </select>
          </div>
        }
      />

      {error && <ErrorBox error={error} />}

      {overview.loading && !overview.data ? (
        <Loading />
      ) : (
        <>
          <Card title={`Overview (${ov.role || '—'})`}>
            <div className="stats-grid">
              {statCards.map((s) => (
                <div className="stat-card" key={s.label}>
                  <div className="stat-value">{s.value ?? 0}</div>
                  <div className="stat-label">{s.label}</div>
                </div>
              ))}
            </div>
          </Card>

          <div className="detail-grid">
            <Card title="Risk distribution (closed sessions)">
              {Object.keys(riskDist).length ? (
                Object.entries(riskDist).map(([lv, n]) => (
                  <BarRow key={lv} label={lv} value={n} max={maxRisk} accent={`fill-${lv.toLowerCase()}`} />
                ))
              ) : (
                <div className="empty">No closed sessions yet.</div>
              )}
            </Card>

            <Card title="Incident review pipeline">
              <div className="summary-strip">
                <div className="summary-item"><strong>{incident.PENDING ?? 0}</strong> pending</div>
                <div className="summary-item"><strong>{incident.CONFIRMED ?? 0}</strong> confirmed</div>
                <div className="summary-item"><strong>{incident.DISMISSED ?? 0}</strong> resolved/dismissed</div>
              </div>
              <p className="muted">Incidents are suspicion-only until a teacher reviews them.</p>
            </Card>
          </div>

          <Card title="Recent activity">
            {activity.length ? (
              <table className="table">
                <thead>
                  <tr>
                    <th>Action</th>
                    <th>Entity</th>
                    <th>Actor</th>
                    <th>When</th>
                  </tr>
                </thead>
                <tbody>
                  {activity.map((a, i) => (
                    <tr key={i}>
                      <td>{a.action}</td>
                      <td className="muted">{a.entity_type ? `${a.entity_type} #${a.entity_id ?? '—'}` : '—'}</td>
                      <td className="muted">{a.actor_email || '—'}</td>
                      <td className="muted">{a.created_at ? fmtDate(a.created_at) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="empty">No system activity yet.</div>
            )}
          </Card>
        </>
      )}

      {drill && (
        <>
          <PageHeader
            title={drill.exam_title || `Exam #${drill.exam_id}`}
            subtitle={`${drill.exam_code || ''} — submitted ${drill.submitted}`}
          />
          <Card title="Score summary">
            <div className="summary-strip">
              <div className="summary-item"><strong>{drill.submitted ?? 0}</strong> submitted</div>
              <div className="summary-item"><strong>{drill.avg_percent != null ? `${drill.avg_percent}%` : '—'}</strong> average</div>
              <div className="summary-item"><strong>{drill.median_percent != null ? `${drill.median_percent}%` : '—'}</strong> median</div>
              <div className="summary-item"><strong>{drill.pass_rate != null ? `${drill.pass_rate}%` : '—'}</strong> pass rate</div>
              <div className="summary-item"><strong>{drill.low_score ?? '—'}</strong> low</div>
              <div className="summary-item"><strong>{drill.high_score ?? '—'}</strong> high</div>
              <div className="summary-item"><strong>{drill.pass_count}</strong> pass</div>
              <div className="summary-item"><strong>{drill.fail_count}</strong> fail</div>
            </div>
          </Card>

          <div className="detail-grid">
            <Card title="Score distribution (10pt bands)">
              {drill.score_distribution?.length ? (
                drill.score_distribution.map((b) => (
                  <BarRow key={`${b.from}-${b.to}`} label={`${b.from}–${b.to}`} value={b.count} max={maxDist} />
                ))
              ) : (
                <div className="empty">No scores yet.</div>
              )}
            </Card>

            <Card title="Event trend (last 10 days)">
              {drill.event_trend?.length ? (
                drill.event_trend.map((b) => (
                  <BarRow key={b.date} label={b.date.slice(5)} value={b.count} max={maxTrend} accent="fill-elevated" />
                ))
              ) : (
                <div className="empty">No AI events in this window.</div>
              )}
            </Card>
          </div>

          <div className="detail-grid">
            <Card title="Question difficulty (facility %)">
              {drill.question_difficulty?.length ? (
                drill.question_difficulty.map((q) => (
                  <BarRow
                    key={q.question_id}
                    label={`Q${(q.order_index ?? 0) + 1} (${q.attempted ?? 0} attempts)`}
                    value={q.facility ?? 0}
                    max={maxDiff}
                    accent={q.facility == null ? '' : q.facility < 40 ? 'fill-high' : q.facility > 75 ? 'fill-normal' : 'fill-attention'}
                  />
                ))
              ) : (
                <div className="empty">No answered questions yet.</div>
              )}
            </Card>

            <Card title="Incident types">
              {Object.keys(drill.incident_summary || {}).length ? (
                (() => {
                  const items = Object.entries(drill.incident_summary || {})
                  const top = Math.max(1, ...items.map(([, v]) => v || 0))
                  return items.map(([t, n]) => <BarRow key={t} label={t} value={n || 0} max={top} accent="fill-high" />)
                })()
              ) : (
                <div className="empty">No incidents recorded.</div>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}