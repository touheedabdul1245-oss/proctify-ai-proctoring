import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '../../api'
import { Loading, ErrorBox, Badge } from '../../components/Ui'
import DetailsTab from './tabs/DetailsTab'
import QuestionsTab from './tabs/QuestionsTab'
import AssignTab from './tabs/AssignTab'
import ScheduleTab from './tabs/ScheduleTab'
import PreviewTab from './tabs/PreviewTab'

const STEPS = [
  { key: 'details', label: 'Details' },
  { key: 'questions', label: 'Questions' },
  { key: 'assign', label: 'Assign' },
  { key: 'schedule', label: 'Schedule & Publish' },
  { key: 'preview', label: 'Preview' },
]

export default function ExamEditor() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [sp, setSp] = useSearchParams()
  const tab = sp.get('tab') || 'details'

  const [exam, setExam] = useState(null)
  const [examId, setExamId] = useState(id ? Number(id) : null)
  const [loading, setLoading] = useState(Boolean(id))
  const [error, setError] = useState(null)
  const [actionError, setActionError] = useState(null)

  const load = () => {
    if (!examId) return
    setLoading(true)
    api(`/exams/${examId}`)
      .then((e) => {
        setExam(e)
        setError(null)
      })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (examId) load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [examId])

  function setTab(t) {
    setSp({ tab: t })
  }

  function afterCreate(e) {
    setExam(e)
    setExamId(e.id)
    navigate(`/teacher/exams/${e.id}?tab=questions`, { replace: true })
  }

  function act(fn, then) {
    setActionError(null)
    fn()
      .then((res) => {
        if (res) setExam((prev) => ({ ...prev, ...res }))
        load()
        then && then(res)
      })
      .catch((err) => setActionError(errorMessage(err)))
  }

  if (error) {
    return (
      <div>
        <ErrorBox error={error} />
        <button className="btn btn-ghost" onClick={() => navigate('/teacher/exams')}>
          Back to exams
        </button>
      </div>
    )
  }

  if (loading && (!exam || exam.id !== examId)) {
    return <Loading />
  }

  const activeIndex = STEPS.findIndex((s) => s.key === tab)
  const current = activeIndex < 0 ? 0 : activeIndex
  const locked = !examId

  function stepClass(idx) {
    if (locked) return idx === 0 ? 'active' : 'locked'
    if (idx === current) return 'active'
    if (idx < current) return 'done'
    return 'pending'
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>{examId ? (exam?.title || 'Exam') : 'New Exam'}</h1>
          <p className="muted">
            {exam ? (
              <>
                <span className="mono">{exam.exam_code}</span> · <Badge status={exam.status} /> ·{' '}
                {exam.is_published ? 'Published' : 'Not published'} · {exam.question_count} questions ·{' '}
                {exam.total_marks} marks
              </>
            ) : (
              'Create the exam details first, then add questions, assign students, schedule and publish.'
            )}
          </p>
        </div>
        <div className="page-actions">
          <button className="btn btn-ghost" onClick={() => navigate('/teacher/exams')}>
            Back to exams
          </button>
        </div>
      </div>

      <div className="stepper" role="tablist" aria-label="Exam setup steps">
        {STEPS.map((s, i) => (
          <div
            key={s.key}
            role="tab"
            aria-selected={i === current}
            aria-disabled={locked && i !== 0}
            className={`step ${stepClass(i)} ${locked && i !== 0 ? 'locked' : ''}`}
            onClick={!locked || i === 0 ? () => setTab(s.key) : undefined}
          >
            <span className="step-dot">{i < current && !locked ? '✓' : i + 1}</span>
            <span className="step-label">
              <span className="step-num">Step {i + 1}</span>
              {s.label}
            </span>
            {i < STEPS.length - 1 && <span className="step-line" />}
          </div>
        ))}
      </div>

      {actionError && <ErrorBox error={actionError} />}

      {examId ? (
        <>
          {exam && tab === 'details' && <DetailsTab exam={exam} onSaved={load} onCreated={afterCreate} />}
          {exam && tab === 'questions' && <QuestionsTab exam={exam} onChanged={load} />}
          {exam && tab === 'assign' && <AssignTab exam={exam} onChanged={load} />}
          {exam && tab === 'schedule' && <ScheduleTab exam={exam} onChanged={load} />}
          {exam && tab === 'preview' && <PreviewTab exam={exam} />}
          {exam && (
            <div className="stepper-nav">
              <button className="btn btn-ghost" disabled={current === 0} onClick={() => setTab(STEPS[current - 1].key)}>
                ← Back
              </button>
              {current < STEPS.length - 1 ? (
                <button className="btn btn-primary" onClick={() => setTab(STEPS[current + 1].key)}>
                  Next: {STEPS[current + 1].label} →
                </button>
              ) : (
                <button className="btn btn-ghost" onClick={() => navigate('/teacher/exams')}>
                  Done
                </button>
              )}
            </div>
          )}
        </>
      ) : (
        <>
          <DetailsTab onCreated={afterCreate} />
          <div className="stepper-nav">
            <p className="muted">Create the exam to unlock the remaining steps.</p>
          </div>
        </>
      )}
    </div>
  )
}