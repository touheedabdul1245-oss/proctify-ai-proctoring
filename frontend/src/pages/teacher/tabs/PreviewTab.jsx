import { Card, Badge, fmtDate } from '../../../components/Ui'

export default function PreviewTab({ exam }) {
  const questions = exam.questions || []

  return (
    <div>
      <Card>
        <h2>{exam.title}</h2>
        <p className="muted">
          {exam.subject || 'No subject'} · {exam.duration_minutes} minutes · {exam.total_marks} marks ·{' '}
          <Badge status={exam.status} /> · {exam.is_published ? 'Published' : 'Draft'}
        </p>
        {exam.description && <p>{exam.description}</p>}
        <p className="muted">
          Schedule: {exam.scheduled_start ? `${fmtDate(exam.scheduled_start)} → ${fmtDate(exam.scheduled_end)}` : 'Not scheduled'}
        </p>
      </Card>

      <Card title={`Questions (${questions.length})`}>
        {!questions.length && <div className="empty">No questions added yet.</div>}
        {questions.map((q, i) => (
          <div className="question-row" key={q.id}>
            <strong>
              {i + 1}. {q.question_text}{' '}
              <span className="muted" style={{ fontWeight: 400 }}>
                ({q.marks} marks)
              </span>
            </strong>
            <ul style={{ margin: '8px 0 0', listStyle: 'none', paddingLeft: 0 }}>
              {['A', 'B', 'C', 'D'].map((o) =>
                q[`option_${o.toLowerCase()}`] ? (
                  <li key={o}>
                    {q.correct_option === o ? '✓ ' : ''}
                    <strong>
                      {o}.
                    </strong>{' '}
                    {q[`option_${o.toLowerCase()}`]}
                  </li>
                ) : null,
              )}
            </ul>
          </div>
        ))}
      </Card>
    </div>
  )
}