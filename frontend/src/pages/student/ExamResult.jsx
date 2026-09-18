import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api } from '../../api'
import { PageHeader, Card, Loading, ErrorBox, fmtDate } from '../../components/Ui'

export default function ExamResult() {
  const { token } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let alive = true
    api(`/student/sessions/${token}/summary`)
      .then((s) => alive && setData(s))
      .catch((e) => alive && setErr(e?.message || 'Could not load result'))
    return () => {
      alive = false
    }
  }, [token])

  if (err) {
    return (
      <div>
        <PageHeader title="Exam result" />
        <Card>
          <ErrorBox error={err} />
          <Link className="btn btn-secondary" to="/student/exams">Back to exams</Link>
        </Card>
      </div>
    )
  }
  if (!data) return <Loading />

  const expired = data.status === 'EXPIRED'

  return (
    <div>
      <PageHeader
        title={expired ? 'Time expired' : 'Exam submitted'}
        subtitle="Your submission was recorded."
      />
      <Card>
        <div className={`success-box ${expired ? 'warn-box' : ''}`} style={{ marginBottom: 14 }}>
          {expired
            ? 'The time limit was reached and your exam was submitted automatically.'
            : 'Your answers have been submitted successfully. You can close this page.'}
        </div>
        <div className="summary-strip">
          <div className="summary-item"><strong>{data.answered_count}</strong> answered</div>
          <div className="summary-item"><strong>{data.unanswered_count}</strong> unanswered</div>
          <div className="summary-item"><strong>{data.marked_count}</strong> marked for review</div>
          <div className="summary-item"><strong>{data.total_questions}</strong> total questions</div>
        </div>
        <table className="table" style={{ maxWidth: 560 }}>
          <tbody>
            <tr>
              <td className="muted" width="160">Status</td>
              <td>{expired ? 'EXPIRED (auto-submit)' : 'SUBMITTED'}</td>
            </tr>
            <tr>
              <td className="muted">Submitted at</td>
              <td>{data.submitted_at ? fmtDate(data.submitted_at) : '—'}</td>
            </tr>
            <tr>
              <td className="muted">Auto-submitted</td>
              <td>{data.auto ? 'Yes' : 'No'}</td>
            </tr>
          </tbody>
        </table>
        <div className="form-actions" style={{ marginTop: 16 }}>
          <Link className="btn btn-secondary" to="/student/exams">Back to my exams</Link>
        </div>
      </Card>
    </div>
  )
}