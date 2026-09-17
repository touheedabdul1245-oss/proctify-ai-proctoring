import { useState } from 'react'
import { api, errorMessage } from '../../../api'
import { Card, Field, ErrorBox } from '../../../components/Ui'

const BASE = { title: '', subject: '', description: '', duration_minutes: 60, total_marks: 0, pass_marks: 25 }

export default function DetailsTab({ exam, onSaved, onCreated }) {
  const editing = Boolean(exam)
  const [form, setForm] = useState(
    editing
      ? {
          title: exam.title,
          subject: exam.subject || '',
          description: exam.description || '',
          duration_minutes: exam.duration_minutes,
          total_marks: exam.total_marks || 0,
          pass_marks: exam.pass_marks ?? '',
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
    setBusy(true)
    setErr(null)
    const body = {
      title: form.title,
      subject: form.subject || null,
      description: form.description || null,
      duration_minutes: Number(form.duration_minutes),
      total_marks: form.total_marks ? Number(form.total_marks) : 0,
      pass_marks: form.pass_marks ? Number(form.pass_marks) : null,
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
        <Field label="Exam title" required>
          <input name="title" value={form.title} onChange={(e) => set('title', e.target.value)} required disabled={frozen} />
        </Field>
        <div className="form-grid">
          <Field label="Subject">
            <input name="subject" value={form.subject} onChange={(e) => set('subject', e.target.value)} disabled={frozen} />
          </Field>
          <Field label="Duration (minutes)" required>
            <input name="duration_minutes" type="number" min={1} value={form.duration_minutes} onChange={(e) => set('duration_minutes', e.target.value)} disabled={frozen} />
          </Field>
        </div>
        <div className="form-grid">
          <Field label="Total marks">
            <input name="total_marks" type="number" min={0} value={form.total_marks} onChange={(e) => set('total_marks', e.target.value)} disabled={frozen} />
          </Field>
          <Field label="Pass marks">
            <input name="pass_marks" type="number" min={0} value={form.pass_marks} onChange={(e) => set('pass_marks', e.target.value)} disabled={frozen} />
          </Field>
        </div>
        <Field label="Description">
          <textarea name="description" rows={3} value={form.description} onChange={(e) => set('description', e.target.value)} disabled={frozen} />
        </Field>
        {frozen && <p className="muted">Editing is locked for {exam.status} exams.</p>}
        <ErrorBox error={err} />
        <div className="form-actions">
          <button className="btn btn-primary" disabled={busy}>
            {busy ? 'Saving…' : editing ? 'Save changes' : 'Create exam (draft)'}
          </button>
        </div>
      </form>
    </Card>
  )
}