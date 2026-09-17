import { useState } from 'react'
import { api } from '../../api'
import { PageHeader, Card, Table, Badge, Modal, Loading, useAsync, fmtDate } from '../../components/Ui'

export default function AssignedExams() {
  const [filter, setFilter] = useState('')
  const list = useAsync(() => api(`/student/exams?include_unpublished=true`), [])
  const [detail, setDetail] = useState(null)

  const cols = [
    { key: 'title', label: 'Exam' },
    { key: 'exam_code', label: 'Code', render: (r) => <span className="mono">{r.exam_code}</span> },
    { key: 'subject', label: 'Subject', render: (r) => r.subject || '—' },
    { key: 'scheduled_start', label: 'Starts', render: (r) => (r.scheduled_start ? fmtDate(r.scheduled_start) : '—') },
    { key: 'scheduled_end', label: 'Ends', render: (r) => (r.scheduled_end ? fmtDate(r.scheduled_end) : '—') },
    { key: 'duration_minutes', label: 'Duration', render: (r) => `${r.duration_minutes} min` },
    { key: 'total_marks', label: 'Marks' },
    { key: 'question_count', label: 'Questions' },
    { key: 'status', label: 'Status', render: (r) => <Badge status={r.status} /> },
    { key: 'published', label: 'Published', render: (r) => (r.is_published ? <Badge status="published" /> : <Badge status="draft" />) },
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
          <Table columns={cols} rows={rows} onRowClick={(r) => setDetail(r)} />
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
          </div>
        )}
      </Modal>
    </div>
  )
}