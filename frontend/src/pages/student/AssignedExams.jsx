import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api'
import { PageHeader, Card, Table, Badge, Modal, Loading, useAsync, fmtDate } from '../../components/Ui'

function useSessionStates(list) {
  const { data, loading, refresh } = useAsync(async () => {
    const exams = list.data || []
    const states = await Promise.all(
      exams.map(async (e) => {
        try {
          const s = await api(`/student/exams/${e.exam_id}/session`)
          return { exam_id: e.exam_id, ...s }
        } catch {
          return { exam_id: e.exam_id, session_token: null, status: null }
        }
      })
    )
    return Object.fromEntries(states.map((s) => [s.exam_id, s]))
  }, [list.data])
  return { states: data || {}, loading, refresh }
}

export default function AssignedExams() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState('')
  const list = useAsync(() => api(`/student/exams?include_unpublished=true`), [])
  const [detail, setDetail] = useState(null)
  const session = useSessionStates(list)

  const cols = [
    { key: 'title', label: 'Exam' },
    { key: 'exam_code', label: 'Code', render: (r) => <span className="mono">{r.exam_code}</span> },
    { key: 'subject', label: 'Subject', render: (r) => r.subject || '—' },
    { key: 'scheduled_start', label: 'Starts', render: (r) => (r.scheduled_start ? fmtDate(r.scheduled_start) : '—') },
    { key: 'scheduled_end', label: 'Ends', render: (r) => (r.scheduled_end ? fmtDate(r.scheduled_end) : '—') },
    { key: 'duration_minutes', label: 'Duration', render: (r) => `${r.duration_minutes} min` },
    { key: 'total_marks', label: 'Marks' },
    { key: 'question_count', label: 'Questions' },
    {
      key: 'action',
      label: 'Action',
      render: (r) => {
        const st = session.states[r.exam_id] || {}
        const open = r.is_published && ['SCHEDULED', 'AVAILABLE', 'ACTIVE'].includes(r.status)
        let label = '—'
        let target = null
        if (st.status === 'ACTIVE') {
          label = 'Resume exam'
          target = `/student/exam/${st.session_token}`
        } else if (st.status === 'SUBMITTED' || st.status === 'EXPIRED') {
          label = st.status === 'EXPIRED' ? 'Expired' : 'Submitted'
          target = `/student/result/${st.session_token}`
        } else if (open) {
          label = st.status === 'PREPARING' ? 'Continue' : 'Start exam'
          target = `/student/exams/${r.exam_id}`
        }
        if (!target) return <span className="muted">{label}</span>
        return (
          <button
            className="btn btn-primary btn-sm"
            onClick={(e) => {
              e.stopPropagation()
              navigate(target)
            }}
          >
            {label}
          </button>
        )
      },
    },
  ]

  const rows = (list.data || []).filter((r) => !filter || r.status === filter)

  return (
    <div>
      <PageHeader title="My Exams" subtitle="Exams assigned to you (directly or via your batch)" />
      <Card>
        <div style={{ maxWidth: 260, marginBottom: 10 }}>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All statuses</option>
            <option value="DRAFT">DRAFT</option>
            <option value="SCHEDULED">SCHEDULED</option>
            <option value="AVAILABLE">AVAILABLE</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="COMPLETED">COMPLETED</option>
            <option value="ARCHIVED">ARCHIVED</option>
          </select>
        </div>
        {list.loading ? (
          <Loading />
        ) : (
          <Table
            columns={cols}
            rows={rows}
            rowKey="exam_id"
            onRowClick={(r) => setDetail(r)}
          />
        )}
      </Card>

      <Modal open={Boolean(detail)} onClose={() => setDetail(null)} title={detail?.title}>
        {detail && (
          <div>
            <div className="summary-strip">
              <div className="summary-item">
                <strong>{detail.duration_minutes}</strong> minutes
              </div>
              <div className="summary-item">
                <strong>{detail.total_marks}</strong> marks
              </div>
              <div className="summary-item">
                <strong>{detail.question_count}</strong> questions
              </div>
            </div>
            {detail.description && <p>{detail.description}</p>}
            <table className="table">
              <tbody>
                <tr>
                  <td className="muted" width="160">
                    Exam code
                  </td>
                  <td className="mono">{detail.exam_code}</td>
                </tr>
                <tr>
                  <td className="muted">Status</td>
                  <td>
                    <Badge status={detail.status} />
                  </td>
                </tr>
                <tr>
                  <td className="muted">Starts</td>
                  <td>{fmtDate(detail.scheduled_start)}</td>
                </tr>
                <tr>
                  <td className="muted">Ends</td>
                  <td>{fmtDate(detail.scheduled_end)}</td>
                </tr>
                <tr>
                  <td className="muted">Assigned via</td>
                  <td>{detail.assigned_via.join(', ') || '—'}</td>
                </tr>
              </tbody>
            </table>
            <div className="form-actions">
              {detail.is_published && ['SCHEDULED', 'AVAILABLE', 'ACTIVE'].includes(detail.status) && (
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    const st = session.states[detail.exam_id] || {}
                    if (st.status === 'ACTIVE') navigate(`/student/exam/${st.session_token}`)
                    else navigate(`/student/exams/${detail.exam_id}`)
                  }}
                >
                  {session.states[detail.exam_id]?.status === 'ACTIVE' ? 'Resume exam' : 'Start exam'}
                </button>
              )}
              <button className="btn btn-ghost" onClick={() => setDetail(null)}>
                Close
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}