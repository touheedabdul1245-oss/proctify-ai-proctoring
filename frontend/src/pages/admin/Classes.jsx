import { useState } from 'react'
import { api, errorMessage } from '../../api'
import { PageHeader, Card, Table, Modal, Field, ErrorBox, Loading, useAsync } from '../../components/Ui'

const EMPTY = { code: '', name: '', description: '' }

export default function Classes() {
  const list = useAsync(() => api('/classes'), [])
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [err, setErr] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setErr(null)
    try {
      await api('/classes', { method: 'POST', body: form })
      setCreating(false)
      setForm(EMPTY)
      list.refresh()
    } catch (e2) {
      setErr(errorMessage(e2))
    }
  }

  const cols = [
    { key: 'code', label: 'Code', render: (r) => <span className="mono">{r.code}</span> },
    { key: 'name', label: 'Batch / Class name' },
    { key: 'description', label: 'Description', render: (r) => r.description || '—' },
    { key: 'student_count', label: 'Students' },
  ]

  return (
    <div>
      <PageHeader
        title="Classes / Batches"
        subtitle="Groups used for bulk enrollment and batch exam assignment"
        actions={
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            + New class / batch
          </button>
        }
      />
      <Card>
        {list.loading ? <Loading /> : <Table columns={cols} rows={list.data || []} />}
      </Card>

      <Modal open={creating} onClose={() => setCreating(false)} title="New class / batch">
        <form onSubmit={submit}>
          <div className="form-grid">
            <Field label="Code" required>
              <input value={form.code} onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))} placeholder="e.g. SE-2026-A" required />
            </Field>
            <Field label="Name" required>
              <input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} required />
            </Field>
          </div>
          <Field label="Description">
            <textarea value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} rows={3} />
          </Field>
          <ErrorBox error={err} />
          <div className="form-actions">
            <button type="button" className="btn btn-ghost" onClick={() => setCreating(false)}>
              Cancel
            </button>
            <button className="btn btn-primary">Create</button>
          </div>
        </form>
      </Modal>
    </div>
  )
}