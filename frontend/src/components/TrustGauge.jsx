import { useEffect, useMemo, useRef, useState } from 'react'

// Trust Score 0-100 visual. The value is ALWAYS the authoritative number from
// the backend (/…/monitor/overview, /…/trust, ProctoringSignalOut). This
// component only animates/paints it — it never computes the score itself.
const BANDS = {
  NORMAL: { color: '#2dd4a7', from: 80, label: 'Normal' },
  ATTENTION: { color: '#f5b83d', from: 60, label: 'Attention' },
  ELEVATED: { color: '#f08a4b', from: 40, label: 'Elevated' },
  HIGH: { color: '#f0555a', from: 0, label: 'High risk' },
}

function bandFor(level) {
  const lv = String(level || 'NORMAL').toUpperCase()
  return BANDS[lv] || BANDS.NORMAL
}

function useCountUp(target, duration = 700) {
  const [value, setValue] = useState(0)
  const raf = useRef(0)
  const prev = useRef(0)
  useEffect(() => {
    const from = prev.current
    const to = Number(target) || 0
    const t0 = performance.now()
    const step = (t) => {
      const p = Math.min(1, (t - t0) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      setValue(from + (to - from) * eased)
      if (p < 1) raf.current = requestAnimationFrame(step)
      else prev.current = to
    }
    raf.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf.current)
  }, [target, duration])
  return value
}

export default function TrustGauge({
  score,
  level,
  delta,
  source,
  size = 132,
  showLabel = true,
  animate = true,
}) {
  const band = bandFor(level)
  const raw = Number(score)
  const safe = Number.isFinite(raw) ? Math.max(0, Math.min(100, raw)) : 0
  const animated = useCountUp(safe, animate ? 800 : 0)
  const value = animate ? animated : safe

  const r = (size - 14) / 2
  const cx = size / 2
  const circ = 2 * Math.PI * r
  const gradId = useMemo(
    () => `trust-grad-${Math.random().toString(36).slice(2, 8)}`,
    [],
  )
  const deltaUp = Number(delta) > 0
  const deltaDown = Number(delta) < 0

  return (
    <div
      className="trust-gauge"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`Trust Score ${Math.round(value)} — ${band.label}`}
    >
      <svg width={size} height={size} className="trust-gauge-svg">
        <defs>
          <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={band.color} />
            <stop offset="100%" stopColor={band.color} stopOpacity="0.55" />
          </linearGradient>
        </defs>
        <circle
          className="trust-gauge-track"
          cx={cx} cy={cx} r={r}
          fill="none"
          strokeWidth="9"
        />
        <circle
          cx={cx} cy={cx} r={r}
          fill="none"
          stroke={band.color}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={circ - (value / 100) * circ}
          transform={`rotate(-90 ${cx} ${cx})`}
          className="trust-gauge-arc"
        />
      </svg>
      <div className="trust-gauge-inner">
        <div className="trust-gauge-score" style={{ color: band.color }}>
          {Math.round(value)}
        </div>
        <div className="trust-gauge-max">/ 100</div>
      </div>
      {(deltaUp || deltaDown) && (
        <span className={`trust-gauge-delta ${deltaDown ? 'down' : ''}`}>
          {deltaDown ? '▼' : '▲'} {Math.abs(Number(delta)).toFixed(1)}
        </span>
      )}
      {showLabel && (
        <div className="trust-gauge-meta">
          <span className="trust-gauge-band">{band.label}</span>
          {source && <span className="trust-gauge-source">{source}</span>}
        </div>
      )}
    </div>
  )
}

export function trustBandColor(level) {
  return bandFor(level).color
}