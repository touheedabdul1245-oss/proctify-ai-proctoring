import { useState } from 'react'
import { api, errorMessage } from '../../../api'
import { Card, Field, Modal, ErrorBox, Loading, useAsync } from '../../../components/Ui'

export default function AssignTab({ exam, onChanged }) {
  const students = useAsync(() => api('/students'), [])
  const classes = useAsync(() => api('/classes'), [])

  const [selStudents, setSelStudents] = useState([])
  const [selClasses, setSelClasses] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [summary, setSummary] = useState(null)

  const assigned = exam.assigned_students || []
  const assignedIds = new Set(assigned.map((s) => s.id))
  const assignedClasses = exam.assigned_batches || []
  const assignedClassIds = new Set(assignedClasses.map((c) => c.id))

  const batchCoverage = assignedClasses.reduce((acc, c) => acc + Number(c.student_count || 0), 0)
  const coverage = assigned.length + batchCoverage

  const available = (students.data || []).filter((s) => !assignedIds.has(s.id))
  const availableClasses = (classes.data || []).filter((c) => !assignedClassIds.has(c.id))

  async function addAssignment() {
    if (!selStudents.length && !selClasses.length) return
    setBusy(true)
    setErr(null)
    setSummary(null)
    try {
      const res = await api(`/exams/${exam.id}/assign`, {
        method: 'POST',
        body: { student_ids: selStudents, class_ids: selClasses },
      })
      if (res && res.assignment_summary) setSummary(res.assignment_summary)
      setSelStudents([])
      setSelClasses([])
      onChanged()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function removeStudents(ids) {
    setBusy(true)
    setErr(null)
    try {
      await api(`/exams/${exam.id}/unassign`, { method: 'POST', body: { student_ids: ids, class_ids: [] } })
      onChanged()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function removeClasses(ids) {
    setBusy(true)
    setErr(null)
    try {
      await api(`/exams/${exam.id}/unassign`, { method: 'POST', body: { student_ids: [], class_ids: ids } })
      onChanged()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const locked = exam.status === 'ARCHIVED' || exam.status === 'COMPLETED'

  return (
    <div>
      <Card
        title={`Assign students or batches (${coverage} student${coverage === 1 ? '' : 's'} covered)`}
      >
        {locked && <p className="muted">Assignment is locked for {exam.status} exams.</p>}
        <div className="summary-strip">
          <div className="summary-item">
            <strong>{assigned.length}</strong> direct students
          </div>
          <div className="summary-item">
            <strong>{assignedClasses.length}</strong> batches ({batchCoverage} students)
          </div>
          <div className="summary-item">
            <strong>{coverage}</strong> total covered
          </div>
        </div>
        {summary && (
          <div className="success-box">
            <strong>Assignment result</strong> — added {summary.added_students || 0} student
            {summary.added_students === 1 ? '' : 's'}, {summary.added_batches || 0} batch
            {summary.added_batches === 1 ? '' : 'es'}
            {Boolean(summary.duplicate_students || summary.duplicate_batches) && (
              <> · {summary.duplicate_students || 0} duplicate handl
              {summary.duplicate_students === 1 ? '' : 'es'} ignored, {summary.duplicate_batches || 0} duplicate batch
              {summary.duplicate_batches === 1 ? '' : 'es'} ignored</>
            )}
            {Boolean(summary.invalid_students || summary.invalid_batches) && (
              <> · {summary.invalid_students || 0} invalid, {summary.invalid_batches || 0} invalid batch
              {summary.invalid_batches === 1 ? '' : 'es'}</>
            )}
            .
          </div>
        )}
        <ErrorBox error={err} />
        <div className="form-grid" style={{ marginBottom: 10 }}>
          <Field label="Add students">
            {students.loading ? (
              <Loading />
            ) : (
              <select multiple size={6} value={selStudents} onChange={(e) => setSelStudents([...e.target.selectedOptions].map((o) => Number(o.value)))}>
                {available.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.student_id} — {s.full_name} {s.class_name ? `(${s.class_name})` : ''}
                  </option>
                ))}
                {!available.length && <option disabled>No unassigned students</option>}
              </select>
            )}
          </Field>
          <Field label="Add batches / classes">
            {classes.loading ? (
              <Loading />
            ) : (
              <select multiple size={6} value={selClasses} onChange={(e) => setSelClasses([...e.target.selectedOptions].map((o) => Number(o.value)))}>
                {availableClasses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code} — {c.name} ({c.student_count} students)
                  </option>
                ))}
                {!availableClasses.length && <option disabled>No unassigned batches</option>}
              </select>
            )}
          </Field>
        </div>
        {!locked && (
          <div className="form-actions" style={{ justifyContent: 'flex-start' }}>
            <button className="btn btn-primary" onClick={addAssignment} disabled={busy || (!selStudents.length && !selClasses.length)}>
              Add selected
            </button>
          </div>
        )}
      </Card>

      <Card title="Individually assigned students">
        {assigned.length ? (
          <AssignList items={assigned} onRemove={locked ? null : (ids) => removeStudents(ids)} />
        ) : (
          <div className="empty">No individually assigned students.</div>
        )}
      </Card>

      <Card title="Assigned batches">
        {assignedClasses.length ? (
          <AssignList items={assignedClasses} onRemove={locked ? null : (ids) => removeClasses(ids)} />
        ) : (
          <div className="empty">No batches assigned. Assigning a batch covers all its students.</div>
        )}
      </Card>
    </div>
  )
}

function AssignList({ items, onRemove }) {
  const [sel, setSel] = useState([])
  return (
    <div>
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 30 }}>
              <input type="checkbox" checked={sel.length === items.length} onChange={(e) => setSel(e.target.checked ? items.map((i) => i.id) : [])} />
            </th>
            <th>{items[0]?.student_id !== undefined ? 'Student ID' : 'Code'}</th>
            <th>{items[0]?.student_id !== undefined ? 'Name' : 'Batch name'}</th>
            <th>Class</th>
          </tr>
        </thead>
        <tbody>
          {items.map((i) => (
            <tr key={i.id}>
              <td>
                <input
                  type="checkbox"
                  checked={sel.includes(i.id)}
                  onChange={(e) => setSel((p) => (e.target.checked ? [...p, i.id] : p.filter((x) => x !== i.id)))}
                />
              </td>
              <td className="mono">{i.student_id ?? i.code}</td>
              <td>{i.full_name ?? i.name}</td>
              <td>{i.class_name ?? `${i.student_count} students`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {onRemove && items.length > 0 && (
        <div className="form-actions" style={{ justifyContent: 'flex-start' }}>
          <button className="btn btn-danger btn-sm" disabled={!sel.length} onClick={() => onRemove(sel)}>
            Remove selected
          </button>
        </div>
      )}
    </div>
  )
}