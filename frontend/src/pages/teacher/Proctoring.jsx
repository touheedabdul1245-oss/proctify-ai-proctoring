import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api'
import { PageHeader, Card, Loading, useAsync } from '../../components/Ui'

const LEVEL_CLASS = {
  NORMAL: 'risk-pill risk-normal',
  ATTENTION: 'risk-pill risk-attention',
  ELEVATED: 'risk-pill risk-elevated',
  HIGH: 'risk-pill risk-high',
}

export default function Proctoring() {
  const bands = useAsync(() => api('/proctoring/bands'), [])

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
          {Array.isArray(b.levels) && b.levels.length
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

        <p className="muted">
          Live risk signals for running exams are shown on the{' '}
          <Link to="/teacher/monitor">live monitor</Link>.
        </p>
      </Card>
    </div>
  )
}
