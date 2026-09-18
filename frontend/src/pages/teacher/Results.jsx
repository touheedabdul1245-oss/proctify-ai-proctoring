import { useMemo, useState } from 'react'
import { api, getToken } from '../../api'
import { PageHeader, Card, Badge, Loading, ErrorBox, Modal, useAsync, fmtDate } from '../../components/Ui'

const LEVEL_CLASS = {
  NORMAL: 'risk-pill risk-normal',
  ATTENTION: 'risk-pill risk-attention',
  ELEVATED: 'risk-pill risk-elevated',
  HIGH: 'risk-pill risk-high',
}

function RiskPill({ level }) {
  const lv = String(level || 'NORMAL').toUpperCase()
  return <span className={LEVEL_CLASS[lv] || LEVEL_CLASS.NORMAL}>{lv}</span>
}

async function exportCsv(examId) {
  const q = examId ? `?exam_id=${examId}` : ''
  const resp = await fetch(`/api/teacher/results/export${q}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  })
  if (!resp.ok) throw new Error(`Export failed (HTTP ${resp.status})`)
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `proctify-results-${examId || 'all'}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export default function Results() {
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [exportExam, setExportExam] = useState('')
  const [busy, setBusy] = useState(false)
  const [notify, setNotify] = useState('')

  const exams = useAsync(() => api('/exams'), [])
  const list = useAsync(
    () => api(`/teacher/results${filter === 'all' ? '' : `?published=${filter === 'published'}`}`),
    [filter],
  )

  const examMap = useMemo(() => {
    const m = {}
    for (const e of exams.data || []) m[e.id] = e
    return m
  }, [exams.data])

  async function openDetail(row) {
    setSelected(row)
    setDetail(null)
    try {
      const d = await api(`/teacher/results/${row.result_id}`)
      setDetail(d)
    } catch (e) {
      setDetail({ error: e })
    }
  }

  async function doPublish(d) {
    setBusy(true)
    setNotify('')
    try {
      const out = await api(`/teacher/results/${d.result_id}/publish`, { method: 'POST' })
      setNotify(out.published ? 'Result published — the student has been notified.' : 'Publish failed.')
      list.refresh()
      openDetail(d)
    } catch (e) {
      setNotify(e?.message || 'Publish failed.')
    } finally {
      setBusy(false)
    }
  }

  const rows = list.data || []

  return (
    <div>
      <PageHeader
        title="Results"
        subtitle="Scorecards across your exams — publish a result to release it to the student."
        actions={
          <div className="segment-row">
            <select className="input" value={exportExam} onChange={(e) => setExportExam(e.target.value)}>
              <option value="">Export all results…</option>
              {exams.data?.map((e) => (
                <option key={e.id} value={e.id}>Export — {e.title}</option>
              ))}
            </select>
            <button
              className="btn btn-secondary"
              disabled={busy}
              onClick={async () => {
                setBusy(true)
                try {
                  await exportCsv(exportExam ? Number(exportExam) : undefined)
                } catch (e) {
                  setNotify(e?.message || 'Export failed.')
                } finally {
                  setBusy(false)
                }
              }}
            >
              Export CSV
            </button>
          </div>
        }
      />

      {notify && <div className="success-box">{notify}</div>}

      <Card title={`Scorecards (${rows.length})`}>
        <div className="mon-toolbar">
          <select className="input" value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All results</option>
            <option value="published">Published</option>
            <option value="unpublished">Awaiting release</option>
          </select>
          <span className="muted mon-count">Grading happens automatically on submission; release is manual.</span>
        </div>
        {list.loading ? (
          <Loading />
        ) : list.error ? (
          <ErrorBox error={list.error} />
        ) : rows.length ? (
          <table className="table">
            <thead>
              <tr>
                <th>Student</th>
                <th>Exam</th>
                <th>Score</th>
                <th>%</th>
                <th>Result</th>
                <th>Status</th>
                <th>Submitted</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const ex = examMap[r.exam_id]
                return (
                  <tr key={r.result_id}>
                    <td>
                      <div>{r.student_name}</div>
                      <div className="muted">{r.student_email}</div>
                    </td>
                    <td>
                      {ex ? `${ex.title} (${ex.exam_code})` : `Exam #${r.exam_id}`}
                    </td>
                    <td>{r.score ?? '—'} / {r.total_marks ?? '—'}</td>
                    <td>{r.percent != null ? `${r.percent}%` : '—'}</td>
                    <td><Badge status={r.result_status || 'GRADED'} /></td>
                    <td>{r.published ? <Badge status="published" /> : <Badge status="pending" />}</td>
                    <td className="muted">{r.submitted_at ? fmtDate(r.submitted_at) : '—'}</td>
                    <td>
                      <button className="btn btn-secondary btn-sm" onClick={() => openDetail(r)}>
                        Review
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : (
          <div className="empty">No results yet — they appear once students submit their exams.</div>
        )}
      </Card>

      <Modal
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={detail ? `${detail.student_name} — ${detail.exam_title || `Exam #${detail.exam_id}`}` : 'Result detail'}
        wide
      >
        {selected && (
          <div>
            {detail?.error && <ErrorBox error={detail.error} />}
            {!detail && <Loading />}
            {detail && !detail.error && (
              <div>
                <div className="detail-stats">
                  <div className="stat-chips">
                    <span className="chip">Score <strong>{detail.score ?? '—'} / {detail.total_marks ?? '—'}</strong></span>
                    <span className="chip">Percent <strong>{detail.percent != null ? `${detail.percent}%` : '—'}</strong></span>
                    <span className="chip"><Badge status={detail.result_status || 'GRADED'} /></span>
                    <span className="chip"><RiskPill level={detail.risk_level} /></span>
                    <span className="chip">Events <strong>{detail.event_count}</strong></span>
                    <span className="chip">Evidence <strong>{detail.evidence_count}</strong></span>
                  </div>
                </div>

                <Card title={`Incidents (${detail.incidents?.length || 0})`}>
                  {detail.incidents?.length ? (
                    detail.incidents.map((i) => (
                      <div className="incident-card" key={i.id}>
                        <div className="incident-head">
                          <span className="incident-type">{i.incident_type}</span>
                          <RiskPill level={i.risk_level} />
                          <span className={`badge badge-review-${String(i.review_status).toLowerCase()}`}>{i.review_status}</span>
                        </div>
                        <div className="incident-desc">{i.description || '—'}</div>
                        <div className="incident-meta muted">{fmtDate(i.created_at)}</div>
                      </div>
                    ))
                  ) : (
                    <div className="empty">No incidents for this session.</div>
                  )}
                </Card>

                <div className="form-actions">
                  <button
                    className="btn btn-primary"
                    disabled={busy || detail.published}
                    onClick={() => doPublish(detail)}
                  >
                    {detail.published ? 'Already published' : 'Publish to student'}
                  </button>
                  <button className="btn btn-ghost" onClick={() => setSelected(null)}>Close</button>
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}