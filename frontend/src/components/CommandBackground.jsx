import { useMemo } from 'react'

// Futuristic animated backdrop: subtle perspective grid + glowing orbs +
// drifting particles. Purely decorative (pointer-events none, aria-hidden).
const ORBS = [
  { top: '6%', left: '8%', size: 420, hue: 212, delay: '0s' },
  { top: '38%', left: '78%', size: 360, hue: 160, delay: '-6s' },
  { top: '70%', left: '28%', size: 300, hue: 280, delay: '-12s' },
  { top: '12%', left: '64%', size: 220, hue: 24, delay: '-4s' },
]

export default function CommandBackground({ dense = false }) {
  const particles = useMemo(() => {
    return Array.from({ length: dense ? 34 : 20 }, (_, i) => {
      const angle = (i / (dense ? 34 : 20)) * Math.PI * 2 + (i % 7) * 0.4
      const dist = 12 + ((i * 37) % 46)
      return {
        left: `${50 + Math.cos(angle) * dist}%`,
        top: `${50 + Math.sin(angle) * dist}%`,
        size: 2 + ((i * 13) % 4),
        delay: `${-((i * 1.7) % 18)}s`,
        dur: `${14 + ((i * 7) % 12)}s`,
      }
    })
  }, [dense])

  return (
    <div className="cmd-bg" aria-hidden="true">
      <div className="cmd-bg-grid" />
      {ORBS.map((o, i) => (
        <div
          key={i}
          className="cmd-bg-orb"
          style={{
            top: o.top,
            left: o.left,
            width: o.size,
            height: o.size,
            background: `radial-gradient(circle at 35% 35%, hsla(${o.hue}, 85%, 60%, 0.16), transparent 65%)`,
            animationDelay: o.delay,
          }}
        />
      ))}
      <div className="cmd-bg-beams" />
      <div className="cmd-bg-particles">
        {particles.map((p, i) => (
          <span
            key={i}
            className="cmd-bg-particle"
            style={{
              left: p.left,
              top: p.top,
              width: p.size,
              height: p.size,
              animationDelay: p.delay,
              animationDuration: p.dur,
            }}
          />
        ))}
      </div>
      <div className="cmd-bg-vignette" />
    </div>
  )
}