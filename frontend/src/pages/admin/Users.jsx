import { useState } from 'react'
import { api, errorMessage } from '../../api'
import { PageHeader, Card, Table, Badge, Modal, Field, ErrorBox, Loading, useAsync, fmtDate } from '../../components/Ui'

const EMPTY = { email: '', password: '', full_name: '', role: 'student', student_id: '', teacher_id: '', class_code: '' }

export default function Users() {
  const [filters, setFilters] = useState({ role: '', q: '' })
  const list = useAsync(
    () => api(`/users?role=${filters.role || ''}&q=${encodeURIComponent(filters.q || '')}`),
    [filters.role, filters.q],
  )

  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [err, setErr] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setErr(null)
    try {
      await api('/users', { method: 'POST', body: form })
      setCreating(false)
      setForm(EMPTY)
      list.refresh()
    } catch (e2) {
      setErr(errorMessage(e2))
    }
  }

  function set(k, v) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  const cols = [
    { key: 'full_name', label: 'Name' },
    { key: 'email', label: 'Email' },
    { key: 'role', label: 'Role', render: (r) => <Badge status={r.role} /> },
    {
      key: 'identifier',
      label: 'ID',
      render: (r) => <span className="mono">{r.student_id || r.teacher_id || '—'}</span>,
    },
    { key: 'class_name', label: 'Class', render: (r) => r.class_name || '—' },
    { key: 'is_active', label: 'Status', render: (r) => (r.is_active ? <Badge status="valid" /> : <Badge status="danger" />) },
    { key: 'created_at', label: 'Created', render: (r) => fmtDate(r.created_at) },
  ]

  return (
    <div>
      <PageHeader
        title="Users"
        subtitle="All accounts by role"
        actions={
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            + New user
          </button>
        }
      />
      <Card>
        <div className="form-grid" style={{ marginBottom: 12 }}>
          <Field label="Role filter">
            <select value={filters.role} onChange={(e) => setFilters((f) => ({ ...f, role: e.target.value }))}>
              <option value="">All roles</option>
              <option value="student">Student</option>
              <option value="teacher">Teacher</option>
              <option value="admin">Admin</option>
            </select>
          </Field>
          <Field label="Search">
            <input value={filters.q} onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))} placeholder="Name or email…" />
          </Field>
        </div>
        {list.loading ? <Loading /> : <Table columns={cols} rows={list.data || []} />}
      </Card>

      <Modal open={creating} onClose={() => setCreating(false)} title="Create user">
        <form onSubmit={submit}>
          <FormBody form={form} set={set} />
          <ErrorBox error={err} />
          <div className="form-actions">
            <button type="button" className="btn btn-ghost" onClick={() => setCreating(false)}>
              Cancel
            </button>
            <button className="btn btn-primary">Create user</button>
          </div>
        </form>
      </Modal>
    </div>
  )
}

function FormBody({ form, set }) {
  return (
    <>
      <div className="form-grid">
        <Field label="Full name" required>
          <input value={form.full_name} onChange={(e) => set('full_name', e.target.value)} required />
        </Field>
        <Field label="Email" required>
          <input type="email" value={form.email} onChange={(e) => set('email', e.target.value)} required />
        </Field>
      </div>
      <div className="form-grid">
        <Field label="Role" required>
          <select value={form.role} onChange={(e) => set('role', e.target.value)} required>
            <option value="student">Student</option>
            <option value="teacher">Teacher</option>
            <option value="admin">Admin</option>
          </select>
        </Field>
        <Field label="Password" required>
          <input value={form.password} onChange={(e) => set('password', e.target.value)} placeholder="min 6 chars" required />
        </Field>
      </div>
      {form.role === 'student' && (
        <div className="form-grid">
          <Field label="Student ID" required>
            <input value={form.student_id} onChange={(e) => set('student_id', e.target.value)} placeholder="e.g. S-2026-001" required />
          </Field>
          <Field label="Class code">
            <input value={form.class_code} onChange={(e) => set('class_code', e.target.value)} placeholder="e.g. SE-2026-A" />
          </Field>
        </div>
      )}
      {form.role === 'teacher' && (
        <Field label="Teacher ID">
          <input value={form.teacher_id} onChange={(e) => set('teacher_id', e.target.value)} placeholder="e.g. T-1001 (optional)" />
        </Field>
      )}
    </>
  )
}