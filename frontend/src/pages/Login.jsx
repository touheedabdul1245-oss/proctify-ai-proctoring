import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { errorMessage } from '../api'
import { ErrorBox } from '../components/Ui'

export default function Login() {
  const { user, login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  if (user) return <Navigate to={`/${user.role}`} replace />

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      const u = await login(email, password)
      navigate(location.state?.from?.pathname || `/${u.role}`, { replace: true })
    } catch (e2) {
      setErr(errorMessage(e2))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <span className="brand-mark big">P</span>
          <h1>PROCTIFY</h1>
          <p className="muted">AI-Assisted Online Examination System</p>
        </div>
        <form onSubmit={submit}>
          <label className="field">
            <span className="field-label">Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoFocus
            />
          </label>
          <label className="field">
            <span className="field-label">Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </label>
          <ErrorBox error={err} />
          <button className="btn btn-primary btn-block" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <div className="login-hint">
          <p className="muted">Demo accounts</p>
          <ul>
            <li>admin@proctify.dev / Admin@123</li>
            <li>teacher@proctify.dev / Teacher@123</li>
          </ul>
        </div>
      </div>
    </div>
  )
}