import { useState } from 'react'
import { api, errorMessage } from '../../api'
import { PageHeader, Card, Table, Badge, Modal, Field, ErrorBox, Loading, useAsync, fmtDate } from '../../components/Ui'

const EMPTY = { student_id: '', full_name: '', email: '', password: '', class_code: '' }

export default function Students() {
  const [q, setQ] = useState('')
  const list = useAsync(() => api(`/students?q=${encodeURIComponent(q)}`), [q])

  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [err, setErr] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setErr(null)
    try {
      await api('/students', { method: 'POST', body: form })
      setCreating(false)
      setForm(EMPTY)
      list.refresh()
    } catch (e2) {
      setErr(errorMessage(e2))
    }
  }

  const cols = [
    { key: 'student_id', label: 'Student ID', render: (r) => <span className="mono">{r.student_id}</span> },
    { key: 'full_name', label: 'Name' },
    { key: 'email', label: 'Email' },
    { key: 'class_name', label: 'Class', render: (r) => r.class_name || '—' },
    { key: 'is_active', label: 'Status', render: (r) => (r.is_active ? <Badge status="valid" /> : <Badge status="danger" />) },
    { key: 'created_at', label: 'Enrolled', render: (r) => fmtDate(r.created_at) },
  ]

  return (
    <div>
      <PageHeader
        title="Students"
        subtitle="Individual student records"
        actions={
          <>
            <button className="btn btn-ghost" onClick={() => (window.location.href = '/admin/enrollment')}>
              Bulk enrollment
            </button>
            <button className="btn btn-primary" onClick={() => setCreating(true)}>
              + Add student
            </button>
          </>
        }
      />
      <Card>
        <Field label="Search students">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="ID, name, or email…" />
        </Field>
        {list.loading ? <Loading /> : <Table columns={cols} rows={list.data || []} />}
      </Card>

      <Modal open={creating} onClose={() => setCreating(false)} title="Add student">
        <form onSubmit={submit}>
          <div className="form-grid">
            <Field label="Student ID" required>
              <input value={form.student_id} onChange={(e) => setForm((f) => ({ ...f, student_id: e.target.value }))} required />
            </Field>
            <Field label="Full name" required>
              <input value={form.full_name} onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} required />
            </Field>
          </div>
          <div className="form-grid">
            <Field label="Email" required>
              <input type="email" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} required />
            </Field>
            <Field label="Class code">
              <input value={form.class_code} onChange={(e) => setForm((f) => ({ ...f, class_code: e.target.value }))} placeholder="e.g. SE-2026-A" />
            </Field>
          </div>
          <Field label="Password">
            <input
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
              placeholder="defaults to Student@123"
            />
          </Field>
          <ErrorBox error={err} />
          <div className="form-actions">
            <button type="button" className="btn btn-ghost" onClick={() => setCreating(false)}>
              Cancel
            </button>
            <button className="btn btn-primary">Create student</button>
          </div>
        </form>
      </Modal>
    </div>
  )
}