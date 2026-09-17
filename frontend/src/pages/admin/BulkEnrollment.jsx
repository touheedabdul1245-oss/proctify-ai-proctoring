import { useRef, useState } from 'react'
import { api, errorMessage } from '../../api'
import { PageHeader, Card, Table, Badge, Loading, useAsync } from '../../components/Ui'

const SAMPLE_CSV = `student_id,name,email,class
S-2026-101,Alice Smith,alice.smith@proctify.dev,SE-2026-A
S-2026-102,Bob Jones,bob.jones@proctify.dev,SE-2026-A
S-2026-103,Cara Lee,cara.lee@proctify.dev, CS-2025-B`

export default function BulkEnrollment() {
  const history = useAsync(() => api('/bulk-enrollment/history'), [])

  const [step, setStep] = useState('upload') // upload | preview | done
  const [busy, setBusy] = useState(false)
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [summary, setSummary] = useState(null)
  const [err, setErr] = useState(null)
  const fileRef = useRef()

  function pickFile(e) {
    const f = e.target.files?.[0]
    if (!f) return
    setFile(f)
    setErr(null)
  }

  async function upload() {
    if (!file) {
      setErr('Choose a .xlsx or .csv file first.')
      return
    }
    setBusy(true)
    setErr(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await api('/bulk-enrollment/upload', { method: 'POST', isForm: true, body: fd })
      setPreview(res)
      setStep('preview')
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function confirm() {
    setBusy(true)
    setErr(null)
    try {
      const res = await api(`/bulk-enrollment/confirm?preview_id=${preview.preview_id}`, { method: 'POST' })
      setSummary(res)
      setStep('done')
      history.refresh()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function cancelPreview() {
    try {
      await api(`/bulk-enrollment/cancel/${preview.preview_id}`, { method: 'POST' })
    } catch {
      /* noop */
    }
    setPreview(null)
    setStep('upload')
    setFile(null)
    if (fileRef.current) fileRef.current.value = ''
    history.refresh()
  }

  if (step === 'preview' && preview) {
    return <PreviewView p={preview} onConfirm={confirm} onCancel={cancelPreview} busy={busy} err={err} />
  }

  if (step === 'done' && summary) {
    return <DoneView summary={summary} onReset={() => { setStep('upload'); setSummary(null); setFile(null); if (fileRef.current) fileRef.current.value = '' }} />
  }

  return (
    <div>
      <PageHeader title="Bulk Enrollment" subtitle="Upload an Excel/CSV roster, validate, preview duplicates, then import" />
      <Card title="1 — Choose file">
        <p className="muted" style={{ marginTop: 0 }}>
          Required columns: <code>student_id</code>, <code>name</code>, <code>email</code>. Optional: <code>class</code>.
          Max {2000} rows.
        </p>
        <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" onChange={pickFile} />
        <div className="form-actions">
          <button className="btn btn-primary" onClick={upload} disabled={busy}>
            {busy ? 'Uploading…' : 'Upload & validate'}
          </button>
        </div>
        {err && <div className="error-box">{err}</div>}
      </Card>

      <Card title="2 — Template">
        <p className="muted">Sample CSV format:</p>
        <pre className="mono">{SAMPLE_CSV}</pre>
      </Card>

      <Card title="Import history">
        {history.loading ? (
          <Loading />
        ) : (
          <Table
            columns={[
              { key: 'filename', label: 'File' },
              { key: 'total_rows', label: 'Rows' },
              { key: 'imported_count', label: 'Imported' },
              { key: 'duplicate_rows', label: 'Duplicates' },
              { key: 'invalid_rows', label: 'Invalid' },
              { key: 'summary', label: 'Summary' },
              { key: 'created_at', label: 'Date', render: (r) => new Date(r.created_at).toLocaleString() },
            ]}
            rows={history.data || []}
          />
        )}
      </Card>
    </div>
  )
}

function PreviewView({ p, onConfirm, onCancel, busy, err }) {
  const colDefs = [
    { key: 'row_number', label: 'Row' },
    { key: 'student_id', label: 'Student ID', render: (r) => <span className="mono">{r.student_id}</span> },
    { key: 'full_name', label: 'Name' },
    { key: 'email', label: 'Email' },
    { key: 'class_code', label: 'Class', render: (r) => r.class_code || '—' },
    { key: 'status', label: 'Status', render: (r) => <Badge status={r.status} /> },
    { key: 'error_message', label: 'Message', render: (r) => <span className="muted">{r.error_message || '—'}</span> },
  ]

  return (
    <div>
      <PageHeader
        title="Validation preview"
        subtitle="Review rows flagged as duplicates or invalid before importing"
        actions={
          <>
            <button className="btn btn-ghost" onClick={onCancel}>
              Back
            </button>
            <button className="btn btn-primary" onClick={onConfirm} disabled={busy || p.valid_rows === 0}>
              {busy ? 'Importing…' : `Import ${p.valid_rows} valid students`}
            </button>
          </>
        }
      />
      <Card>
        <div className="summary-strip">
          <div className="summary-item">
            <strong>{p.total_rows}</strong> total rows
          </div>
          <div className="summary-item">
            <strong className="sucess">{p.valid_rows}</strong> valid — will import
          </div>
          <div className="summary-item">
            <strong>{p.duplicate_rows}</strong> duplicates — skipped
          </div>
          <div className="summary-item">
            <strong style={{ color: 'var(--danger)' }}>{p.invalid_rows}</strong> invalid — skipped
          </div>
        </div>
        {err && <div className="error-box">{err}</div>}
      </Card>

      <Card title={`All rows (${p.total_rows})`}>
        <Table columns={colDefs} rows={[...p.new, ...p.duplicates, ...p.invalid]} />
      </Card>
      <Card title={`Duplicate rows (${p.duplicates.length})`}>
        {p.duplicates.length ? <Table columns={colDefs} rows={p.duplicates} /> : <div className="empty">No duplicates.</div>}
      </Card>
      <Card title={`Invalid rows (${p.invalid.length})`}>
        {p.invalid.length ? <Table columns={colDefs} rows={p.invalid} /> : <div className="empty">No invalid rows.</div>}
      </Card>
    </div>
  )
}

function DoneView({ summary, onReset }) {
  return (
    <div>
      <PageHeader title="Import complete" actions={<button className="btn btn-ghost" onClick={onReset}>New import</button>} />
      <Card>
        <div className="summary-strip">
          <div className="summary-item">
            <strong className="sucess">{summary.imported}</strong> students imported
          </div>
          <div className="summary-item">
            <strong>{summary.skipped_duplicates}</strong> duplicates skipped
          </div>
          <div className="summary-item">
            <strong>{summary.invalid}</strong> invalid skipped
          </div>
        </div>
        {summary.errors?.length > 0 && (
          <ul>
            {summary.errors.map((m, i) => (
              <li key={i} className="muted">
                {m}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}