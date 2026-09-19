import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { errorMessage } from '../api'
import { ErrorBox } from '../components/Ui'
import CommandBackground from '../components/CommandBackground'

export default function Login() {
  const { user, login } = useAuth()
  const [username, setUsername] = useState('')
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
      const u = await login(username, password)
      navigate(location.state?.from?.pathname || `/${u.role}`, { replace: true })
    } catch (e2) {
      setErr(errorMessage(e2))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <CommandBackground dense />
      <div className="login-card page-enter">
        <div className="login-brand">
          <span className="brand-mark big">P</span>
          <h1>PROCTIFY</h1>
          <p className="muted">AI-Assisted Examination Command Center</p>
        </div>
        <form onSubmit={submit}>
          <label className="field">
            <span className="field-label">Username</span>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter your username"
              autoComplete="username"
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
            {busy ? 'Authenticating…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}