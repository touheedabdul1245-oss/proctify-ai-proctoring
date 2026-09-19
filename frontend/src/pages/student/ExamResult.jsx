import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api } from '../../api'
import { PageHeader, Card, Loading, ErrorBox, Badge, fmtDate } from '../../components/Ui'

const OPTIONS = ['A', 'B', 'C', 'D']

function RiskPill({ level }) {
  const lv = String(level || 'NORMAL').toUpperCase()
  const cls = { NORMAL: 'risk-pill risk-normal', ATTENTION: 'risk-pill risk-attention', ELEVATED: 'risk-pill risk-elevated', HIGH: 'risk-pill risk-high' }
  return <span className={cls[lv] || cls.NORMAL}>{lv}</span>
}

export default function ExamResult() {
  const { token } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let alive = true
    api(`/student/sessions/${token}/result`)
      .then((d) => alive && setData(d))
      .catch((e) => {
        if (e?.status === 409) {
          // session not closed yet — redirect to the exam intro
          return alive && navigate('/student/exams')
        }
        alive && setErr(e?.message || 'Could not load result')
      })
    return () => {
      alive = false
    }
  }, [token, navigate])

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

  const expired = data.session_status === 'EXPIRED'
  const terminated = data.session_status === 'TERMINATED'
  const published = Boolean(data.published)
  const monitoring = data.monitoring || {}

  return (
    <div>
      <PageHeader
        title={data.exam_title || 'Exam result'}
        subtitle={`${data.exam_code || ''} · ${data.session_token || ''}`.trim()}
        actions={<Link className="btn btn-secondary" to="/student/exams">Back to exams</Link>}
      />

      {terminated && (
        <div className="error-box" style={{ marginBottom: 14 }}>
          This exam session was <strong>terminated by the invigilator</strong>. Your answers were preserved, but
          no score was produced and the exam can no longer be re-opened.
        </div>
      )}

      {!published && !terminated && (
        <div className="warn-box" style={{ marginBottom: 14 }}>
          Your result has been graded but is <strong>awaiting teacher review and release</strong>. You can
          see your submission below; the official score will appear once published.
        </div>
      )}

      <Card title="Summary">
        <div className="summary-strip">
          <div className="summary-item"><strong>{data.score ?? '—'}</strong> marks scored</div>
          <div className="summary-item"><strong>{data.total_marks ?? '—'}</strong> total</div>
          <div className="summary-item"><strong>{data.percent != null ? `${data.percent}%` : '—'}</strong> percentage</div>
          <div className="summary-item"><Badge status={published ? data.result_status || 'GRADED' : 'pending'} /></div>
        </div>
        <table className="table" style={{ maxWidth: 600 }}>
          <tbody>
            <tr>
              <td className="muted" width="160">Status</td>
              <td>{expired ? 'EXPIRED (auto-submit)' : terminated ? 'TERMINATED' : data.session_status || 'SUBMITTED'}</td>
            </tr>
            <tr>
              <td className="muted">Submitted at</td>
              <td>{data.submitted_at ? fmtDate(data.submitted_at) : '—'}</td>
            </tr>
            <tr>
              <td className="muted">Published</td>
              <td>{published ? (data.published_at ? fmtDate(data.published_at) : 'Yes') : 'Not yet'}</td>
            </tr>
          </tbody>
        </table>
      </Card>

      {monitoring && Object.keys(monitoring).length > 0 && (
        <Card title="Proctoring summary">
          <div className="summary-strip">
            <div className="summary-item"><RiskPill level={monitoring.risk_level} /></div>
            <div className="summary-item"><strong>{monitoring.event_count ?? 0}</strong> AI events</div>
            <div className="summary-item"><strong>{monitoring.pending_incidents ?? 0}</strong> pending</div>
            <div className="summary-item"><strong>{monitoring.confirmed_incidents ?? 0}</strong> confirmed</div>
            <div className="summary-item"><strong>{monitoring.evidence_count ?? 0}</strong> evidence</div>
          </div>
          <p className="muted">
            AI proctoring produces suspicion-only signals reviewed by teachers — your grade is decided by the
            answer key, not by monitoring flags.
          </p>
        </Card>
      )}

      <Card title={`Answer review (${data.questions?.length || 0})`}>
        {data.questions?.length ? (
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th>Question</th>
                <th>Marks</th>
                <th>Your answer</th>
                {published && <th>Correct</th>}
                {published && <th>Awarded</th>}
              </tr>
            </thead>
            <tbody>
              {data.questions.map((q) => {
                const sel = q.selected_option ? OPTIONS.indexOf(q.selected_option) : -1
                const corr = q.correct_option ? OPTIONS.indexOf(q.correct_option) : -1
                return (
                  <tr key={q.question_id}>
                    <td className="muted">{q.order_index != null ? q.order_index + 1 : '—'}</td>
                    <td>{q.question_text}</td>
                    <td>{q.marks}</td>
                    <td>
                      {sel >= 0 ? (
                        <span className={published ? (q.is_correct ? 'ok-text' : 'err-text') : ''}>
                          {q.selected_option}
                          {published && q.is_correct ? ' ✓' : published ? ' ✗' : ''}
                        </span>
                      ) : (
                        <span className="muted">Unanswered</span>
                      )}
                    </td>
                    {published && (
                      <td>
                        {corr >= 0 ? <span className="ok-text">{q.correct_option}</span> : <span className="muted">—</span>}
                      </td>
                    )}
                    {published && <td>{q.marks_awarded ?? 0}</td>}
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : (
          <div className="empty">No answer detail available.</div>
        )}
      </Card>

      <div className="form-actions" style={{ marginTop: 16 }}>
        <Link className="btn btn-secondary" to="/student/results">All my results</Link>
        <button className="btn btn-ghost" onClick={() => navigate('/student/exams')}>
          Back to exams
        </button>
      </div>
    </div>
  )
}