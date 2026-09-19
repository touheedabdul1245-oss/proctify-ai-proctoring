import { useState } from 'react'
import { api, errorMessage } from '../../../api'
import { Card, Field, Badge, Modal, ErrorBox, fmtDate } from '../../../components/Ui'

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
  const [okMsg, setOkMsg] = useState(null)
  const [confirm, setConfirm] = useState(null)

  async function run(path, body, successMsg) {
    setBusy(true)
    setErr(null)
    setOkMsg(null)
    try {
      await api(path, { method: 'POST', body })
      setOkMsg(successMsg)
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
    }, 'Exam scheduled.')
  }

  function reschedule() {
    if (!start || !end) {
      setErr('Both start and end times are required.')
      return
    }
    run(`/exams/${exam.id}/reschedule`, {
      scheduled_start: new Date(start).toISOString(),
      scheduled_end: new Date(end).toISOString(),
    }, 'Exam rescheduled.')
  }

  function publish() {
    run(`/exams/${exam.id}/publish`, {}, 'Exam published — assigned students can now see it.')
  }

  function terminate() {
    setConfirm('terminate')
  }

  function doTerminate() {
    setConfirm(null)
    run(`/exams/${exam.id}/terminate`, {}, 'Exam terminated. Active sessions were closed and answers preserved (no grading).')
  }

  function cancel() {
    run(`/exams/${exam.id}/cancel`, {}, 'Exam cancelled — no longer visible to students.')
  }

  function archive() {
    run(`/exams/${exam.id}/status`, { target_status: 'ARCHIVED' }, 'Exam archived.')
  }

  const terminal = ['COMPLETED', 'TERMINATED', 'CANCELLED', 'ARCHIVED'].includes(exam.status)
  const frozen = exam.status === 'ACTIVE' || terminal

  return (
    <div>
      <Card title="Exam window">
        <p className="muted">
          Current: {exam.scheduled_start ? `${fmtDate(exam.scheduled_start)} → ${fmtDate(exam.scheduled_end)}` : 'Not scheduled yet'}
          {' · Status: '}
          <Badge status={exam.status} />
        </p>
        {exam.status === 'AVAILABLE' && (
          <p className="warn-box" style={{ fontWeight: 600 }}>
            The window is open — students can start the exam right now. Use Terminate below to end it early.
          </p>
        )}
        {exam.status === 'ACTIVE' && (
          <p className="warn-box" style={{ fontWeight: 600 }}>
            Students are actively taking this exam. Terminating closes it immediately and preserves current answers without grading.
          </p>
        )}
        <div className="form-grid">
          <Field label="Starts at" required>
            <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} disabled={frozen} />
          </Field>
          <Field label="Ends at" required>
            <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} disabled={frozen} />
          </Field>
        </div>
        <ErrorBox error={err} />
        {okMsg && <div className="success-box">{okMsg}</div>}
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

      <Card title="Publish & state actions">
        {okMsg && !confirm && <div className="success-box">{okMsg}</div>}
        <div className="form-actions" style={{ justifyContent: 'flex-start', marginBottom: 8 }}>
          {['DRAFT', 'SCHEDULED'].includes(exam.status) && (
            <button className="btn btn-primary" onClick={publish} disabled={busy}>
              Publish exam
            </button>
          )}
          {['AVAILABLE', 'ACTIVE'].includes(exam.status) && (
            <button
              className="btn btn-danger"
              onClick={terminate}
              disabled={busy}
              title="Immediately end the exam; preserve answers without grading"
            >
              Terminate exam
            </button>
          )}
          {['DRAFT', 'SCHEDULED', 'AVAILABLE'].includes(exam.status) && (
            <button className="btn btn-outline-danger" onClick={cancel} disabled={busy}>
              Cancel exam
            </button>
          )}
          {exam.status === 'COMPLETED' && (
            <button className="btn btn-secondary" onClick={archive} disabled={busy}>
              Archive
            </button>
          )}
        </div>
        {exam.is_published ? (
          <p className="muted" style={{ marginBottom: 0 }}>
            <Badge status="published" /> This exam is visible to assigned students.
          </p>
        ) : (
          <p className="muted" style={{ marginBottom: 0 }}>
            Not published — students cannot see it yet. Verify the window and publish when ready.
          </p>
        )}
        {terminal && (
          <p className="muted" style={{ marginTop: 10, marginBottom: 0 }}>
            This exam is {exam.status.toLowerCase()} and can no longer be re-opened.
          </p>
        )}
      </Card>

      <Modal open={confirm === 'terminate'} onClose={() => setConfirm(null)} title="Terminate exam?">
        <p>
          This immediately closes <strong>{exam.title}</strong> permanently.
        </p>
        <ul className="wizard-step-body" style={{ paddingLeft: 20, margin: '10px 0' }}>
          <li>All active and preparing sessions are marked <strong>terminated</strong>.</li>
          <li>Student answers are preserved, but <strong>no score or result</strong> is produced.</li>
          <li>Streaming telemetry stops; the exam cannot be re-opened.</li>
        </ul>
        <div className="form-actions" style={{ justifyContent: 'flex-end' }}>
          <button className="btn btn-ghost" onClick={() => setConfirm(null)}>
            Keep exam
          </button>
          <button className="btn btn-danger" onClick={doTerminate} disabled={busy}>
            Yes, terminate exam
          </button>
        </div>
      </Modal>
    </div>
  )
}