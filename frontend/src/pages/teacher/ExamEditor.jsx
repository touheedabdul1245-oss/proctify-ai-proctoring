import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '../../api'
import { Loading, ErrorBox, Badge, fmtDate } from '../../components/Ui'
import DetailsTab from './tabs/DetailsTab'
import QuestionsTab from './tabs/QuestionsTab'
import AssignTab from './tabs/AssignTab'
import ScheduleTab from './tabs/ScheduleTab'
import PreviewTab from './tabs/PreviewTab'

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

  // initial load once examId known
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

  const tabs = [
    { key: 'details', label: 'Details' },
    { key: 'questions', label: 'Questions' },
    { key: 'assign', label: 'Assign' },
    { key: 'schedule', label: 'Schedule & Publish' },
    { key: 'preview', label: 'Preview' },
  ]

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
              'Fill details, add questions, assign students, schedule, then publish.'
            )}
          </p>
        </div>
        <div className="page-actions">
          <button className="btn btn-ghost" onClick={() => navigate('/teacher/exams')}>
            Back to exams
          </button>
        </div>
      </div>

      {actionError && <ErrorBox error={actionError} />}

      {examId ? (
        <>
          <div className="tabs">
            {tabs.map((t) => (
              <button key={t.key} className={'tab' + (tab === t.key ? ' active' : '')} onClick={() => setTab(t.key)}>
                {t.label}
              </button>
            ))}
          </div>
          {exam && tab === 'details' && <DetailsTab exam={exam} onSaved={load} onCreated={afterCreate} />}
          {exam && tab === 'questions' && <QuestionsTab exam={exam} onChanged={load} />}
          {exam && tab === 'assign' && <AssignTab exam={exam} onChanged={load} />}
          {exam && tab === 'schedule' && <ScheduleTab exam={exam} onChanged={load} act={act} />}
          {exam && tab === 'preview' && <PreviewTab exam={exam} />}
        </>
      ) : (
        <DetailsTab onCreated={afterCreate} />
      )}
    </div>
  )
}