import { api } from '../../api'
import { Card, Loading, useAsync, PageHeader } from '../../components/Ui'

export default function Profile() {
  const p = useAsync(() => api('/profile'), [])

  if (p.loading) return <Loading />
  const u = p.data.user || {}

  return (
    <div>
      <PageHeader title="My Profile" subtitle="Account and enrollment information" />
      <Card>
        <div className="stats-grid">
          <div className="stat-card" style={{ gridColumn: 'span 2' }}>
            <div className="stat-value" style={{ fontSize: 20 }}>
              {u.full_name}
            </div>
            <div className="stat-label">@{u.username}</div>
            <div className="muted" style={{ fontSize: 13 }}>{u.email}</div>
          </div>
        </div>
        <table className="table">
          <tbody>
            <tr>
              <td width="200" className="muted">
                Student ID
              </td>
              <td className="mono">{p.data.student_id || '—'}</td>
            </tr>
            <tr>
              <td className="muted">Class / Batch</td>
              <td>
                {p.data.class_name ? `${p.data.class_name} (${p.data.class_code})` : '—'}
              </td>
            </tr>
            <tr>
              <td className="muted">Role</td>
              <td>{u.role}</td>
            </tr>
            <tr>
              <td className="muted">Account status</td>
              <td>{u.is_active ? 'Active' : 'Deactivated'}</td>
            </tr>
            <tr>
              <td className="muted">Enrollment records</td>
              <td>{p.data.enrolled_total ?? 0}</td>
            </tr>
            <tr>
              <td className="muted">Assigned exams</td>
              <td>{p.data.assigned_exam_count ?? 0}</td>
            </tr>
          </tbody>
        </table>
      </Card>
    </div>
  )
}