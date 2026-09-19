import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api'
import { Card, Loading, PageHeader, StatCard } from '../../components/Ui'
import AnimatedCounter from '../../components/AnimatedCounter'
import { ErrorState, EmptyState } from '../../components/Status'

export default function StudentDashboard() {
  const stats = useAsyncSafe(() => api('/dashboard/stats'))

  return (
    <div>
      <PageHeader title="Student Dashboard" subtitle="Your assigned examinations" />
      {stats.status === 'loading' ? (
        <Loading />
      ) : stats.status === 'error' ? (
        <ErrorState error={stats.error} onRetry={stats.refresh} />
      ) : (
        <>
          <div className="stats-grid">
            <StatCard accent="brand" label="Assigned Exams" value={<AnimatedCounter value={stats.data?.counts?.assigned_exams ?? 0} />} />
            <StatCard accent="ok" label="Available to take" value={<AnimatedCounter value={stats.data?.counts?.available ?? 0} />} />
            <StatCard label="Upcoming" value={<AnimatedCounter value={stats.data?.counts?.upcoming ?? 0} />} />
            <StatCard label="Published" value={<AnimatedCounter value={stats.data?.counts?.published_exams ?? 0} />} />
          </div>

          <Card title="Find your exam">
            {(stats.data?.counts?.available ?? 0) > 0 ? (
              <div className="segment-row">
                <Link className="btn btn-primary" to="/student/exams">
                  View my exams
                </Link>
                <Link className="btn btn-secondary" to="/student/profile">
                  My profile
                </Link>
              </div>
            ) : (
              <EmptyState
                title="Nothing available right now"
                hint="When a teacher publishes an exam assigned to you, it will appear here and on the My Exams page."
                action={
                  <Link className="btn btn-secondary btn-sm" to="/student/exams">
                    Go to My Exams
                  </Link>
                }
              />
            )}
          </Card>
        </>
      )}
    </div>
  )
}

function useAsyncSafe(fn) {
  const [state, setState] = useState({ status: 'loading', data: null, error: null })
  const [tick, setTick] = useState(0)
  const refresh = () => setTick((t) => t + 1)
  useEffect(() => {
    let alive = true
    fn()
      .then((data) => alive && setState({ status: 'done', data, error: null }))
      .catch((error) => alive && setState({ status: 'error', data: null, error }))
    return () => {
      alive = false
    }
  }, [tick, fn])
  return { ...state, refresh }
}