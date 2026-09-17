import { Link } from 'react-router-dom'
import { api } from '../../api'
import { StatCard, Card, Loading, useAsync, PageHeader } from '../../components/Ui'

export default function StudentDashboard() {
  const stats = useAsync(() => api('/dashboard/stats'), [])
  if (stats.loading) return <Loading />
  const c = stats.data.counts || {}

  return (
    <div>
      <PageHeader title="Student Dashboard" subtitle="Your assigned examinations" />
      <div className="stats-grid">
        <StatCard label="Assigned Exams" value={c.assigned_exams ?? 0} accent />
        <StatCard label="Available to take" value={c.available ?? 0} />
        <StatCard label="Upcoming" value={c.upcoming ?? 0} />
        <StatCard label="Published" value={c.published_exams ?? 0} />
      </div>
      <Card title="Actions">
        <div className="segment-row">
          <Link className="btn btn-primary" to="/student/exams">
            View my exams
          </Link>
          <Link className="btn btn-secondary" to="/student/profile">
            My profile
          </Link>
        </div>
      </Card>
    </div>
  )
}