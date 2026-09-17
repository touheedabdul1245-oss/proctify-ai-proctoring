import { useState } from 'react'
import { api, errorMessage } from '../../../api'
import { Card, Field, Modal, ErrorBox, Loading } from '../../../components/Ui'

const EMPTY_OPTIONS = [
  { option: 'A', text: '' },
  { option: 'B', text: '' },
  { option: 'C', text: '' },
  { option: 'D', text: '' },
]

export default function QuestionsTab({ exam, onChanged }) {
  const [modal, setModal] = useState(null) // null | 'add' | qid
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [editing, setEditing] = useState(null)

  async function saveQ(e) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    const options = editing.options.filter((o) => o.text.trim())
    if (options.length < 2) {
      setErr('At least 2 options are required.')
      setBusy(false)
      return
    }
    const body = {
      question_text: editing.question_text,
      marks: Number(editing.marks) || 1,
      order_index: Number(editing.order_index) || 0,
      options,
      correct_option: editing.correct_option,
      negative_marks: Number(editing.negative_marks) || 0,
    }
    try {
      if (modal === 'add') await api(`/exams/${exam.id}/questions`, { method: 'POST', body })
      else await api(`/exams/${exam.id}/questions/${modal}`, { method: 'PUT', body })
      setModal(null)
      onChanged()
    } catch (e2) {
      setErr(errorMessage(e2))
    } finally {
      setBusy(false)
    }
  }

  async function del(qid) {
    if (!confirm('Delete this question?')) return
    setErr(null)
    try {
      await api(`/exams/${exam.id}/questions/${qid}`, { method: 'DELETE' })
      onChanged()
    } catch (e2) {
      setErr(errorMessage(e2))
    }
  }

  function openAdd() {
    setEditing({
      question_text: '',
      marks: 1,
      order_index: exam.questions.length + 1,
      options: EMPTY_OPTIONS.map((o) => ({ ...o })),
      correct_option: 'A',
      negative_marks: 0,
    })
    setErr(null)
    setModal('add')
  }

  function openEdit(q) {
    setEditing({
      question_text: q.question_text,
      marks: q.marks,
      order_index: q.order_index,
      options: [
        { option: 'A', text: q.option_a || '' },
        { option: 'B', text: q.option_b || '' },
        { option: 'C', text: q.option_c || '' },
        { option: 'D', text: q.option_d || '' },
      ],
      correct_option: q.correct_option,
      negative_marks: q.negative_marks || 0,
    })
    setErr(null)
    setModal(q.id)
  }

  function setEdit(k, v) {
    setEditing((e) => ({ ...e, [k]: v }))
  }

  const locked = !['DRAFT', 'SCHEDULED'].includes(exam.status)

  return (
    <Card title={`Questions (${exam.questions?.length || 0})`}>
      {locked && <p className="muted">Questions are locked for {exam.status} exams.</p>}
      {!locked && (
        <div className="form-actions" style={{ justifyContent: 'flex-start', marginBottom: 12 }}>
          <button className="btn btn-primary" onClick={openAdd}>
            + Add MCQ question
          </button>
        </div>
      )}

      {!exam.questions?.length && <div className="empty">No questions yet. Add the first MCQ.</div>}

      {exam.questions?.map((q, idx) => (
        <div className="question-row" key={q.id}>
          <div className="page-header" style={{ marginBottom: 8 }}>
            <div>
              <strong>
                Q{idx + 1}. {q.question_text}
              </strong>
              <div className="muted" style={{ fontSize: 12.5 }}>
                {q.marks} mark{q.marks > 1 ? 's' : ''} · correct: {q.correct_option}
                {q.negative_marks ? ` · negative: ${q.negative_marks}` : ''}
              </div>
            </div>
            {!locked && (
              <div className="page-actions">
                <button className="btn btn-sm btn-ghost" onClick={() => openEdit(q)}>
                  Edit
                </button>
                <button className="btn btn-sm btn-danger" onClick={() => del(q.id)}>
                  Delete
                </button>
              </div>
            )}
          </div>
          <ul style={{ margin: 0, columns: 2 }}>
            {['A', 'B', 'C', 'D'].map((o) =>
              q[`option_${o.toLowerCase()}`] ? (
                <li key={o}>
                  <strong>{o}.</strong> {q[`option_${o.toLowerCase()}`]}
                </li>
              ) : null,
            )}
          </ul>
        </div>
      ))}

      <Modal open={Boolean(modal)} onClose={() => setModal(null)} title={modal === 'add' ? 'Add MCQ question' : 'Edit question'}>
        {editing && (
          <form onSubmit={saveQ}>
            <Field label="Question text" required>
              <textarea rows={3} value={editing.question_text} onChange={(e) => setEdit('question_text', e.target.value)} required />
            </Field>
            <div className="form-grid">
              <Field label="Marks" required>
                <input type="number" min={0} value={editing.marks} onChange={(e) => setEdit('marks', e.target.value)} required />
              </Field>
              <Field label="Order">
                <input type="number" min={0} value={editing.order_index} onChange={(e) => setEdit('order_index', e.target.value)} />
              </Field>
              <Field label="Negative marks">
                <input type="number" min={0} step="0.25" value={editing.negative_marks} onChange={(e) => setEdit('negative_marks', e.target.value)} />
              </Field>
              <Field label="Correct option" required>
                <select value={editing.correct_option} onChange={(e) => setEdit('correct_option', e.target.value)}>
                  {['A', 'B', 'C', 'D'].map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            {editing.options.map((opt, i) => (
              <div className="option-line" key={opt.option}>
                <span style={{ width: 16, fontWeight: 600 }}>{opt.option}</span>
                <input
                  value={opt.text}
                  onChange={(e) =>
                    setEdit(
                      'options',
                      editing.options.map((o, j) => (j === i ? { ...o, text: e.target.value } : o)),
                    )
                  }
                  placeholder={`Option ${opt.option}`}
                />
              </div>
            ))}
            <ErrorBox error={err} />
            <div className="form-actions">
              <button type="button" className="btn btn-ghost" onClick={() => setModal(null)}>
                Cancel
              </button>
              <button className="btn btn-primary" disabled={busy}>
                {busy ? 'Saving…' : 'Save question'}
              </button>
            </div>
          </form>
        )}
      </Modal>
    </Card>
  )
}