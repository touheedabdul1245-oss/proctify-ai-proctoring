import { useState } from 'react'
import { api, errorMessage } from '../../../api'
import { Card, Field, Badge, ErrorBox, fmtDate } from '../../../components/Ui'

function toLocalInput(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export default function ScheduleTab({ exam, onChanged }) {
  const [start, setStart] = useState(exam.scheduled_start ? toLocalInput(exam.scheduled_start) : '')
  const [end, setEnd] = useState(exam.scheduled_end ? toLocalInput(exam.scheduled_end) : '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function run(path, body, successMsg) {
    setBusy(true)
    setErr(null)
    try {
      await api(path, { method: 'POST', body })
      await onChanged()
    } catch (e2) {
      setErr(errorMessage(e2))
    } finally {
      setBusy(false)
    }
  }

  function schedule() {
    if (!start || !end) {
      setErr('Both start and end times are required.')
      return
    }
    run(`/exams/${exam.id}/schedule`, {
      scheduled_start: new Date(start).toISOString(),
      scheduled_end: new Date(end).toISOString(),
    })
  }

  function reschedule() {
    if (!start || !end) {
      setErr('Both start and end times are required.')
      return
    }
    run(`/exams/${exam.id}/reschedule`, {
      scheduled_start: new Date(start).toISOString(),
      scheduled_end: new Date(end).toISOString(),
    })
  }

  function publish() {
    run(`/exams/${exam.id}/publish`, {})
  }

  function transition(target) {
    run(`/exams/${exam.id}/status`, { target_status: target })
  }

  function cancel() {
    run(`/exams/${exam.id}/cancel`, {})
  }

  const frozen = ['ACTIVE', 'COMPLETED', 'ARCHIVED'].includes(exam.status)

  return (
    <div>
      <Card title="Schedule window">
        <p className="muted">
          Current: {exam.scheduled_start ? `${fmtDate(exam.scheduled_start)} → ${fmtDate(exam.scheduled_end)}` : 'Not scheduled yet'}
          {' · '}
          Status: <Badge status={exam.status} />
        </p>
        <div className="form-grid">
          <Field label="Starts at" required>
            <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
          </Field>
          <Field label="Ends at" required>
            <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
          </Field>
        </div>
        <ErrorBox error={err} />
        {!frozen && (
          <div className="form-actions" style={{ justifyContent: 'flex-start' }}>
            {exam.status === 'DRAFT' && (
              <button className="btn btn-primary" onClick={schedule} disabled={busy}>
                Schedule exam
              </button>
            )}
            {['SCHEDULED', 'AVAILABLE'].includes(exam.status) && (
              <button className="btn btn-secondary" onClick={reschedule} disabled={busy}>
                Reschedule
              </button>
            )}
          </div>
        )}
      </Card>

      <Card title="Publish / state">
        <div className="form-actions" style={{ justifyContent: 'flex-start', marginBottom: 8 }}>
          {['DRAFT', 'SCHEDULED'].includes(exam.status) && (
            <button className="btn btn-primary" onClick={publish} disabled={busy}>
              Publish exam
            </button>
          )}
        </div>
        <div className="form-actions" style={{ justifyContent: 'flex-start' }}>
          {['DRAFT', 'SCHEDULED'].includes(exam.status) && (
            <button className="btn btn-secondary" onClick={() => transition('SCHEDULED')} disabled={busy}>
              Set SCHEDULED (backfill only)
            </button>
          )}
        </div>
        <div className="segment-row">
          {['DRAFT', 'SCHEDULED'].includes(exam.status) && (
            <button className="btn btn-secondary" onClick={() => transition('SCHEDULED')} disabled={busy}>
              Set SCHEDULED
            </button>
          )}
          {exam.status === 'SCHEDULED' && (
            <button className="btn btn-secondary" onClick={() => transition('AVAILABLE')} disabled={busy}>
              Set AVAILABLE
            </button>
          )}
          {exam.status === 'AVAILABLE' && (
            <button className="btn btn-secondary" onClick={() => transition('ACTIVE')} disabled={busy}>
              Set ACTIVE
            </button>
          )}
          {['SCHEDULED', 'AVAILABLE'].includes(exam.status) && (
            <button className="btn btn-secondary" onClick={() => transition('COMPLETED')} disabled={busy}>
              Set COMPLETED
            </button>
          )}
          {exam.status !== 'ARCHIVED' && exam.status !== 'COMPLETED' && (
            <button className="btn btn-danger" onClick={cancel} disabled={busy}>
              Cancel exam
            </button>
          )}
          {exam.status === 'COMPLETED' && (
            <button className="btn btn-danger" onClick={() => transition('ARCHIVED')} disabled={busy}>
              Archive
            </button>
          )}
        </div>
        {exam.is_published ? (
          <p className="muted" style={{ marginBottom: 0 }}>
            This exam is <Badge status="published" /> — visible to assigned students.
          </p>
        ) : (
          <p className="muted" style={{ marginBottom: 0 }}>
            Not published — students cannot see it yet. Publish after scheduling and adding questions.
          </p>
        )}
      </Card>
    </div>
  )
}
