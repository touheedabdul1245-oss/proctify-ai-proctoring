import { Link } from 'react-router-dom'
import { api } from '../../api'
import { StatCard, Card, Loading, useAsync, PageHeader } from '../../components/Ui'

export default function TeacherDashboard() {
  const stats = useAsync(() => api('/dashboard/stats'), [])

  if (stats.loading) return <Loading />
  const c = stats.data.counts || {}

  return (
    <div>
      <PageHeader title="Teacher Dashboard" subtitle="Examination overview" />
      <div className="stats-grid">
        <StatCard label="Total Exams" value={c.total_exams ?? 0} accent />
        <StatCard label="Drafts" value={c.draft ?? 0} />
        <StatCard label="Scheduled" value={c.scheduled ?? 0} />
        <StatCard label="Active" value={c.active ?? 0} />
        <StatCard label="Completed" value={c.completed ?? 0} />
        <StatCard label="Archived" value={c.archived ?? 0} />
        <StatCard label="Questions" value={c.questions ?? 0} />
        <StatCard label="Enrolled Students" value={c.students ?? 0} />
      </div>

      <Card title="Quick actions">
        <div className="segment-row">
          <Link className="btn btn-secondary" to="/teacher/exams">
            Manage exams
          </Link>
          <Link className="btn btn-primary" to="/teacher/exams/new">
            + Create exam
          </Link>
        </div>
      </Card>
    </div>
  )
}