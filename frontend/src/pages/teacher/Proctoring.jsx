import { useState } from 'react'
import { api } from '../../api'
import { PageHeader, Card, Badge, Loading, ErrorBox, useAsync } from '../../components/Ui'

const LEVEL_CLASS = {
  NORMAL: 'risk-pill risk-normal',
  ATTENTION: 'risk-pill risk-attention',
  ELEVATED: 'risk-pill risk-elevated',
  HIGH: 'risk-pill risk-high',
}

export default function Proctoring() {
  const bands = useAsync(() => api('/proctoring/bands'), [])
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)

  async function runProbe() {
    setRunning(true)
    setError(null)
    try {
      const r = await api('/proctoring/ingest', {
        method: 'POST',
        body: {
          session_token: 'demo-teacher-proctoring',
          observation: {
            objects: [{ class_name: 'phone', confidence: 0.92 }],
            face: { available: true, face_count: 1, faces: [] },
            head_pose: {},
            audio: { available: true, speech_detected: false },
            camera_available: true,
          },
        },
      })
      setResult(r)
    } catch (e) {
      setError(e)
    } finally {
      setRunning(false)
    }
  }

  if (bands.loading) return <Loading />
  const b = bands.data || {}

  return (
    <div>
      <PageHeader
        title="Proctoring"
        subtitle="AI proctoring engine — risk bands, hysteresis and suspicion-only signals"
      />

      <Card title="Risk bands contract">
        <div className="stats-grid">
          {[b.levels]?.flatMap?.call?.()
            ? (b.levels || []).map((lv, i) => (
                <div key={lv} className="stat-card">
                  <div className="stat-value">
                    <span className={LEVEL_CLASS[lv] || ''}>{lv}</span>
                  </div>
                  <div className="stat-label">
                    {i < (b.band_upper || []).length
                      ? `band upper ${b.band_upper[i]}`
                      : 'top band'}
                  </div>
                </div>
              ))
            : null}
        </div>
        <p className="muted">
          hysteresis <strong>{b.hysteresis}</strong> · simulate allowed{' '}
          <strong>{String(b.simulate_allowed)}</strong>
        </p>

        <div className="segment-row">
          <button className="btn btn-primary" onClick={runProbe} disabled={running}>
            {running ? 'Running…' : 'Run live proctoring probe'}
          </button>
        </div>

        {error && <ErrorBox error={error} />}
        {result && (
          <Card title="Latest signal">
            <table className="table">
              <tbody>
                <tr>
                  <td className="muted">Risk level</td>
                  <td>
                    <span className={LEVEL_CLASS[result.risk?.level] || ''}>
                      {result.risk?.level}
                    </span>
                  </td>
                </tr>
                <tr>
                  <td className="muted">Index</td>
                  <td>{(result.risk?.index ?? 0).toFixed(3)}</td>
                </tr>
                <tr>
                  <td className="muted">Factors</td>
                  <td>{Object.entries(result.risk?.factors || {}).join(', ') || '—'}</td>
                </tr>
                <tr>
                  <td className="muted">Incident candidates</td>
                  <td>
                    {(result.incident_candidates || []).length} pending review
                    <Badge status="pending" />
                  </td>
                </tr>
              </tbody>
            </table>
          </Card>
        )}
      </Card>
    </div>
  )
}
