import { Link } from 'react-router-dom'
import { api } from '../../api'
import { StatCard, Card, Badge, Loading, useAsync, PageHeader } from '../../components/Ui'

export default function AdminDashboard() {
  const stats = useAsync(() => api('/dashboard/stats'), [])
  const ai = useAsync(() => api('/ai/health'), [])

  if (stats.loading) return <Loading />

  const c = stats.data.counts || {}

  return (
    <div>
      <PageHeader title="Admin Dashboard" subtitle="Platform-wide overview and AI service status" />
      <div className="stats-grid">
        <StatCard label="Total Users" value={c.total_users ?? 0} accent />
        <StatCard label="Students" value={c.students ?? 0} />
        <StatCard label="Teachers" value={c.teachers ?? 0} />
        <StatCard label="Classes / Batches" value={c.classes ?? 0} />
        <StatCard label="Exams" value={c.exams ?? 0} />
        <StatCard label="Enrollments" value={c.enrollments ?? 0} />
        <StatCard label="Bulk Imports" value={c.imports ?? 0} />
      </div>

      <Card title="AI Service Layer — Health">
        {ai.loading ? (
          <Loading />
        ) : !ai.data ? (
          <div className="error-box">{ai.error?.message || 'AI health unavailable'}</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Backend</th>
                <th>Status</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(ai.data).map(([k, v]) => (
                <tr key={k}>
                  <td>
                    <strong>{k.toUpperCase()}</strong>
                  </td>
                  <td>
                    <Badge status={v.status === 'ok' ? 'valid' : v.status === 'unavailable' ? 'danger' : 'warning'} />
                  </td>
                  <td className="muted">
                    {v.loaded ? 'loaded' : 'not loaded'}
                    {v.path ? ` — ${v.path.split(/[\\/]/).pop()}` : ''}
                    {v.note ? ` — ${v.note}` : ''}
                    {v.error ? ` — ${v.error}` : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <div className="stats-grid">
        <Card className="">
          <div className="card-title">Quick actions</div>
          <div className="segment-row">
            <Link className="btn btn-secondary" to="/admin/students">
              Add student
            </Link>
            <Link className="btn btn-secondary" to="/admin/enrollment">
              Bulk enrollment
            </Link>
            <Link className="btn btn-secondary" to="/admin/classes">
              Manage classes
            </Link>
            <Link className="btn btn-secondary" to="/admin/users">
              Manage users
            </Link>
          </div>
        </Card>
      </div>
    </div>
  )
}