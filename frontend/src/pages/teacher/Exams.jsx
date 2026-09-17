import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api'
import { PageHeader, Card, Table, Badge, Loading, useAsync, fmtDate } from '../../components/Ui'

export default function Exams() {
  const [status, setStatus] = useState('')
  const list = useAsync(() => api(`/exams?status=${status}`), [status])
  const navigate = useNavigate()

  const cols = [
    { key: 'title', label: 'Title' },
    { key: 'exam_code', label: 'Code', render: (r) => <span className="mono">{r.exam_code}</span> },
    { key: 'subject', label: 'Subject', render: (r) => r.subject || '—' },
    { key: 'duration_minutes', label: 'Duration', render: (r) => `${r.duration_minutes} min` },
    { key: 'total_marks', label: 'Marks' },
    { key: 'question_count', label: 'Questions' },
    {
      key: 'assigned_student_count',
      label: 'Assigned',
      render: (r) => `+${r.assigned_student_count} direct`,
    },
    { key: 'scheduled_start', label: 'Scheduled', render: (r) => (r.scheduled_start ? fmtDate(r.scheduled_start) : '—') },
    { key: 'status', label: 'Status', render: (r) => <Badge status={r.status} /> },
    { key: 'published', label: 'Published', render: (r) => (r.is_published ? <Badge status="published" /> : <Badge status="draft" />) },
  ]

  return (
    <div>
      <PageHeader
        title="Exams"
        subtitle="Create, edit, schedule, and publish examinations"
        actions={
          <Link className="btn btn-primary" to="/teacher/exams/new">
            + Create exam
          </Link>
        }
      />
      <Card>
        <div style={{ maxWidth: 260, marginBottom: 10 }}>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
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
          <Table columns={cols} rows={list.data || []} onRowClick={(r) => navigate(`/teacher/exams/${r.id}`)} />
        )}
      </Card>
    </div>
  )
}