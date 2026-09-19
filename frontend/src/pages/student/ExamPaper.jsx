import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../../api'
import { useProctoring } from '../../hooks/useProctoring'
import { ErrorBox, Modal } from '../../components/Ui'

const PROCT_LABEL = {
  idle: 'Connecting…',
  active: 'Monitoring',
  'no-camera': 'No camera — noted',
  off: 'Proctoring off',
  done: 'Proctoring stopped',
  error: 'Monitoring error',
}

function ProctoringChip({ status }) {
  return (
    <span className={`proct-chip proct-${status}`}>
      <i className="proct-dot" />
      {PROCT_LABEL[status] || status}
    </span>
  )
}

const OPTIONS = ['A', 'B', 'C', 'D']

function fmtClock(sec) {
  const s = Math.max(0, Math.floor(sec))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  const mm = String(m).padStart(2, '0')
  const sss = String(ss).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${sss}` : `${mm}:${sss}`
}

function Palette({ questions, answers, idx, onPick }) {
  return (
    <div className="q-palette">
      <div className="q-palette-label">Questions</div>
      <div className="q-palette-grid">
        {questions.map((q, i) => {
          const a = answers[q.id]
          const answered = Boolean(a?.selected)
          const marked = Boolean(a?.marked)
          const cls = ['q-pal-item']
          if (i === idx) cls.push('current')
          if (answered) cls.push('answered')
          if (marked) cls.push('marked')
          return (
            <button key={q.id} className={cls.join(' ')} onClick={() => onPick(i)}>
              {i + 1}
            </button>
          )
        })}
      </div>
      <div className="q-palette-legend">
        <span><i className="dot answered" /> Answered</span>
        <span><i className="dot marked" /> Marked</span>
        <span><i className="dot current" /> Current</span>
      </div>
    </div>
  )
}

export default function ExamPaper() {
  const { token } = useParams()
  const navigate = useNavigate()

  const [paper, setPaper] = useState(null)
  const [answers, setAnswers] = useState({})
  const [idx, setIdx] = useState(0)
  const [remaining, setRemaining] = useState(null)
  const [deadline, setDeadline] = useState(null)
  const [saveState, setSaveState] = useState('idle') // idle | saving | saved | offline
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [fatal, setFatal] = useState(null)
  const [starting, setStarting] = useState(true)

  const dirty = useRef(new Map())
  const answersRef = useRef(answers)
  const deadlineRef = useRef(null)
  const paperRef = useRef(null)
  const endedRef = useRef(false)

  answersRef.current = answers
  deadlineRef.current = deadline
  paperRef.current = paper

  const proct = useProctoring(token, { paused: false })

  const goResult = useCallback((s) => {
    if (endedRef.current) return
    endedRef.current = true
    if (s?.status) navigate(`/student/result/${token}`, { state: { status: s.status, auto: s.auto } })
    else navigate(`/student/result/${token}`)
  }, [navigate, token])

  const handleClosed = useCallback(async () => {
    if (endedRef.current) return
    try {
      const s = await api(`/student/sessions/${token}/summary`)
      if (s.status === 'SUBMITTED' || s.status === 'EXPIRED' || s.status === 'TERMINATED') goResult(s)
    } catch {
      goResult(null)
    }
  }, [token, goResult])

  // --- load paper ---
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const p = await api(`/student/sessions/${token}/paper`)
        if (!alive) return
        setPaper(p)
        const map = {}
        for (const a of p.answers) map[a.question_id] = { selected: a.selected_option, marked: a.marked_for_review }
        setAnswers(map)
        setRemaining(p.remaining_seconds ?? 0)
        setDeadline(Date.now() + (p.remaining_seconds ?? 0) * 1000)
        setStarting(false)
      } catch (e) {
        if (!alive) return
        handleClosed()
      }
    })()
    return () => {
      alive = false
    }
  }, [token, handleClosed])

  // --- persist one answer (PUT) ---
  const syncOne = useCallback(async (qid, payload) => {
    try {
      await api(`/student/sessions/${token}/answers/${qid}`, { method: 'PUT', body: payload })
      dirty.current.delete(qid)
      setSaveState((s) => (dirty.current.size === 0 ? 'saved' : 'saving'))
    } catch (e) {
      if (e?.status === 409) {
        endedRef.current = true
        handleClosed()
        return
      }
      setSaveState('offline')
    }
  }, [token, handleClosed])

  // --- flush dirty answers (autosave) ---
  const flushDirty = useCallback(() => {
    if (endedRef.current || dirty.current.size === 0) return Promise.resolve()
    setSaveState('saving')
    const entries = [...dirty.current.entries()]
    const inflight = entries.map(([qid, payload]) =>
      api(`/student/sessions/${token}/answers/${qid}`, { method: 'PUT', body: payload })
        .then(() => {
          dirty.current.delete(qid)
          if (dirty.current.size === 0) setSaveState('saved')
        })
        .catch((e) => {
          if (e?.status === 409) handleClosed()
          else setSaveState('offline')
        }),
    )
    return Promise.allSettled(inflight).then(() => {})
  }, [token, handleClosed])

  const selectOption = useCallback((qid, option) => {
    if (endedRef.current) return
    const cur = answersRef.current[qid] || { selected: null, marked: false }
    const next = { ...cur, selected: option }
    setAnswers((m) => ({ ...m, [qid]: next }))
    dirty.current.set(qid, { selected_option: option, marked_for_review: next.marked })
    setSaveState('saving')
    syncOne(qid, { selected_option: option, marked_for_review: next.marked })
  }, [syncOne])

  const toggleMark = useCallback((qid) => {
    if (endedRef.current) return
    const cur = answersRef.current[qid] || { selected: null, marked: false }
    const next = { ...cur, marked: !cur.marked }
    setAnswers((m) => ({ ...m, [qid]: next }))
    dirty.current.set(qid, { selected_option: next.selected, marked_for_review: next.marked })
    setSaveState('saving')
    syncOne(qid, { selected_option: next.selected, marked_for_review: next.marked })
  }, [syncOne])

  // --- timer ---
  useEffect(() => {
    if (!deadline) return
    const t = setInterval(() => {
      const rem = Math.round((deadlineRef.current - Date.now()) / 1000)
      setRemaining(rem)
      if (rem <= 0 && !endedRef.current) {
        clearInterval(t)
        doAutoSubmit()
      }
    }, 500)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deadline])

  // --- periodic resync + heartbeat + autosave ---
  useEffect(() => {
    if (!token) return
    const t = setInterval(() => {
      if (endedRef.current || !paperRef.current) return
      flushDirty()
      api(`/student/sessions/${token}/paper`)
        .then((p) => {
          if (endedRef.current) return
          setDeadline(Date.now() + (p.remaining_seconds ?? 0) * 1000)
          setRemaining(p.remaining_seconds ?? 0)
          setSaveState((s) => (dirty.current.size === 0 ? 'saved' : s))
        })
        .catch(() => {
          if (endedRef.current) return
          setTimeout(() => {
            api(`/student/sessions/${token}/summary`)
              .then((s) => {
                if (s.status === 'SUBMITTED' || s.status === 'EXPIRED' || s.status === 'TERMINATED') goResult(s)
              })
              .catch(() => {})
          }, 300)
        })
    }, 20000)
    return () => clearInterval(t)
  }, [token, flushDirty, goResult, handleClosed])

  useEffect(() => {
    const warn = (e) => {
      if (endedRef.current) return
      flushDirty()
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [flushDirty])

  async function doAutoSubmit() {
    if (endedRef.current) return
    endedRef.current = true
    await flushDirty()
    try {
      const s = await api(`/student/sessions/${token}/submit`, { method: 'POST' })
      navigate(`/student/result/${token}`, { state: { status: s.status, auto: s.auto } })
    } catch {
      handleClosed()
    }
  }

  async function doSubmit() {
    setConfirmOpen(false)
    if (endedRef.current) return
    endedRef.current = true
    await flushDirty()
    try {
      const s = await api(`/student/sessions/${token}/submit`, { method: 'POST' })
      navigate(`/student/result/${token}`, { state: { status: s.status, auto: s.auto } })
    } catch {
      handleClosed()
    }
  }

  if (fatal) {
    return (
      <div className="exam-shell">
        <div className="card">
          <ErrorBox error={fatal} />
        </div>
      </div>
    )
  }

  if (starting || !paper) {
    return <div className="exam-shell"><div className="page-loading">Loading exam paper…</div></div>
  }

  const q = paper.questions[idx]
  const lowTime = remaining !== null && remaining <= 120

  return (
    <div className="exam-shell">
      <div className="exam-topbar">
        <div className="exam-title">
          <strong>{paper.title}</strong>
          <span className="muted">{paper.question_count} questions · {paper.total_marks} marks</span>
        </div>
        <div className="exam-right">
          <ProctoringChip status={proct.status} />
          <span className={`autosave-status ${saveState === 'offline' ? 'offline' : ''}`}>
            {saveState === 'offline' ? 'Offline — retrying' : saveState === 'saving' ? 'Saving…' : 'Saved'}
          </span>
          <div className={`timer ${lowTime ? 'low' : ''}`}>{fmtClock(remaining)}</div>
        </div>
      </div>

      <div className="exam-body">
        <div className="question-pane">
          {q ? (
            <div className="question-view" key={q.id}>
              <div className="question-meta">
                <span>Question {idx + 1} of {paper.question_count}</span>
                <span className="badge badge-active">{q.marks} mark{q.marks === 1 ? '' : 's'}</span>
                {q.negative_marks > 0 && (
                  <span className="badge badge-duplicate">−{q.negative_marks} if wrong</span>
                )}
              </div>
              <h2 className="question-text">{q.question_text}</h2>
              <div className="option-list">
                {OPTIONS.map((opt, oi) => {
                  const text = q[`option_${opt.toLowerCase()}`]
                  if (!text) return null
                  const sel = answers[q.id]?.selected === opt
                  return (
                    <button
                      key={opt}
                      className={`option ${sel ? 'selected' : ''}`}
                      onClick={() => selectOption(q.id, opt)}
                    >
                      <span className="option-key">{opt}</span>
                      <span className="option-text">{text}</span>
                    </button>
                  )
                })}
              </div>
              <div className="question-foot">
                <button className="btn btn-primary" disabled={idx === 0} onClick={() => setIdx(idx - 1)}>
                  ← Previous
                </button>
                <button
                  className={`btn ${answers[q.id]?.marked ? 'btn-secondary' : 'btn-ghost'}`}
                  onClick={() => toggleMark(q.id)}
                >
                  {answers[q.id]?.marked ? 'Unmark review' : 'Mark for review'}
                </button>
                {idx < paper.question_count - 1 ? (
                  <button className="btn btn-primary" onClick={() => setIdx(idx + 1)}>
                    Next →
                  </button>
                ) : (
                  <button className="btn btn-danger" onClick={() => setConfirmOpen(true)}>
                    Submit exam
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="empty">No questions in this exam.</div>
          )}
        </div>

        <Palette questions={paper.questions} answers={answers} idx={idx} onPick={setIdx} />
      </div>

      <div className="exam-footer">
        <span className="exam-progress">
          Answered {paper.questions.filter((pq) => answers[pq.id]?.selected).length} of {paper.question_count}
          {' '}· {Object.values(answers).filter((a) => a?.marked).length} marked
        </span>
        <button className="btn btn-outline-danger" onClick={() => setConfirmOpen(true)}>
          Submit exam
        </button>
        <button
          className="btn btn-ghost"
          onClick={() => setIdx(Math.max(0, Math.min(paper.question_count - 1, idx + 1)))}
        >
          Next
        </button>
      </div>

      <Modal open={confirmOpen} onClose={() => setConfirmOpen(false)} title="Submit exam?">
        <p>
          You have answered{' '}
          <strong>{paper.questions.filter((pq) => answers[pq.id]?.selected).length}</strong> of{' '}
          <strong>{paper.question_count}</strong> questions.
          {dirty.current.size > 0 && <span> Unsaved changes will be flushed before submitting.</span>}
        </p>
        <p className="muted">You cannot change your answers after submission.</p>
        <div className="form-actions">
          <button className="btn btn-ghost" onClick={() => setConfirmOpen(false)}>Keep working</button>
          <button className="btn btn-danger" onClick={doSubmit}>Submit now</button>
        </div>
      </Modal>

      {saveState === 'offline' && !endedRef.current && (
        <div className="offline-banner">Connection lost — answers are saved locally and will sync automatically.</div>
      )}
    </div>
  )
}