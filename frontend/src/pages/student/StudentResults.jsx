import { useNavigate } from 'react-router-dom'
import { api } from '../../api'
import { PageHeader, Card, Table, Badge, Loading, useAsync, fmtDate } from '../../components/Ui'

export default function StudentResults() {
  const navigate = useNavigate()
  const list = useAsync(() => api('/student/results'), [])

  const cols = [
    { key: 'exam_title', label: 'Exam' },
    { key: 'exam_code', label: 'Code', render: (r) => <span className="mono">{r.exam_code}</span> },
    { key: 'score', label: 'Score', render: (r) => `${r.score ?? '—'} / ${r.total_marks ?? '—'}` },
    { key: 'percent', label: '%', render: (r) => (r.percent != null ? `${r.percent}%` : '—') },
    { key: 'result_status', label: 'Result', render: (r) => <Badge status={r.result_status || 'GRADED'} /> },
    { key: 'published', label: 'Status', render: (r) => (r.published ? <Badge status="published" /> : <Badge status="pending" />) },
    { key: 'published_at', label: 'Published', render: (r) => (r.published_at ? fmtDate(r.published_at) : '—') },
    {
      key: 'action',
      label: '',
      render: (r) =>
        r.session_token ? (
          <button className="btn btn-primary btn-sm" onClick={() => navigate(`/student/result/${r.session_token}`)}>
            View result
          </button>
        ) : null,
    },
  ]

  const publishedRows = (list.data || []).filter((r) => r.published)
  const pendingRows = (list.data || []).filter((r) => !r.published)

  return (
    <div>
      <PageHeader title="My Results" subtitle="Detailed scorecards for every exam you have submitted." />
      {list.loading ? (
        <Loading />
      ) : (
        <>
          <Card title="Published results">
            <Table columns={cols} rows={publishedRows} rowKey="result_id" />
          </Card>
          <Card title="Awaiting release">
            {pendingRows.length ? (
              <Table columns={cols} rows={pendingRows} rowKey="result_id" />
            ) : (
              <div className="empty">Nothing waiting for release.</div>
            )}
          </Card>
        </>
      )}
    </div>
  )
}