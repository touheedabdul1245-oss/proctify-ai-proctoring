import { useState } from 'react'
import { api, errorMessage } from '../../../api'
import { Card, Field, ErrorBox } from '../../../components/Ui'

function toLocalInput(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const BASE = { title: '', subject: '', description: '', total_marks: 0, pass_marks: '', scheduled_start: '', scheduled_end: '' }

export default function DetailsTab({ exam, onSaved, onCreated }) {
  const editing = Boolean(exam)
  const [form, setForm] = useState(
    editing
      ? {
          title: exam.title,
          subject: exam.subject || '',
          description: exam.description || '',
          total_marks: exam.total_marks || 0,
          pass_marks: exam.pass_marks ?? '',
          scheduled_start: toLocalInput(exam.scheduled_start),
          scheduled_end: toLocalInput(exam.scheduled_end),
        }
      : BASE,
  )
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  function set(k, v) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  async function save(e) {
    e.preventDefault()
    if (form.scheduled_start && form.scheduled_end && new Date(form.scheduled_end) <= new Date(form.scheduled_start)) {
      setErr('End time must be after start time.')
      return
    }
    setBusy(true)
    setErr(null)
    const body = {
      title: form.title,
      subject: form.subject || null,
      description: form.description || null,
      total_marks: form.total_marks ? Number(form.total_marks) : 0,
      pass_marks: form.pass_marks ? Number(form.pass_marks) : null,
      scheduled_start: form.scheduled_start ? new Date(form.scheduled_start).toISOString() : null,
      scheduled_end: form.scheduled_end ? new Date(form.scheduled_end).toISOString() : null,
      save_as_draft: true,
    }
    try {
      const res = editing
        ? await api(`/exams/${exam.id}`, { method: 'PUT', body })
        : await api('/exams', { method: 'POST', body })
      if (editing) onSaved && onSaved(res)
      else onCreated && onCreated(res)
    } catch (e2) {
      setErr(errorMessage(e2))
    } finally {
      setBusy(false)
    }
  }

  const frozen = exam && !['DRAFT', 'SCHEDULED'].includes(exam.status)

  return (
    <Card title={editing ? 'Exam details' : 'Create exam'}>
      <form onSubmit={save}>
        <Field label="Exam name" required>
          <input
            name="title"
            value={form.title}
            onChange={(e) => set('title', e.target.value)}
            required
            disabled={frozen}
            placeholder="e.g. Mid-term Mathematics"
          />
        </Field>
        <div className="form-grid">
          <Field label="Subject">
            <input
              name="subject"
              value={form.subject}
              onChange={(e) => set('subject', e.target.value)}
              disabled={frozen}
              placeholder="e.g. Mathematics"
            />
          </Field>
          <Field label="Pass marks">
            <input
              name="pass_marks"
              type="number"
              min={0}
              value={form.pass_marks}
              onChange={(e) => set('pass_marks', e.target.value)}
              disabled={frozen}
              placeholder="e.g. 25"
            />
          </Field>
        </div>
        <div className="form-grid">
          <Field label="Total marks">
            <input
              name="total_marks"
              type="number"
              min={0}
              value={form.total_marks}
              onChange={(e) => set('total_marks', e.target.value)}
              disabled={frozen}
              placeholder="Auto-filled from questions"
            />
          </Field>
          <Field label="Exam starts (window opens)" required={form.scheduled_end ? false : undefined}>
            <input
              name="scheduled_start"
              type="datetime-local"
              value={form.scheduled_start}
              onChange={(e) => set('scheduled_start', e.target.value)}
              disabled={frozen}
            />
          </Field>
          <Field label="Exam ends (window closes)">
            <input
              name="scheduled_end"
              type="datetime-local"
              value={form.scheduled_end}
              onChange={(e) => set('scheduled_end', e.target.value)}
              disabled={frozen}
            />
          </Field>
        </div>
        <Field label="Description">
          <textarea name="description" rows={2} value={form.description} onChange={(e) => set('description', e.target.value)} disabled={frozen} />
        </Field>
        {frozen && <p className="muted">Editing is locked for {exam.status} exams.</p>}
        <ErrorBox error={err} />
        <div className="form-actions">
          <button className="btn btn-primary" disabled={busy}>
            {busy ? 'Saving…' : editing ? 'Save changes' : 'Create exam & continue'}
          </button>
        </div>
      </form>
    </Card>
  )
}