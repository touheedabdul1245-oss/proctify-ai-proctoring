import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { api } from '../api'
import { timeAgo } from '../pages/teacher/monitorUtils'
import CommandBackground from './CommandBackground'

const ICONS = {
  dashboard: '◈',
  exams: '▤',
  create: '⊕',
  proctoring: '◎',
  monitor: '◉',
  results: '▦',
  analytics: '◔',
  users: '◍',
  students: '☰',
  enrollment: '⇪',
  classes: '▣',
  mine: '▤',
  profile: '◈',
}

const NAV = {
  admin: [
    { to: '/admin', label: 'Dashboard', icon: 'dashboard', end: true },
    { to: '/admin/users', label: 'Users', icon: 'users' },
    { to: '/admin/students', label: 'Students', icon: 'students' },
    { to: '/admin/enrollment', label: 'Bulk Enrollment', icon: 'enrollment' },
    { to: '/admin/classes', label: 'Classes / Batches', icon: 'classes' },
  ],
  teacher: [
    { to: '/teacher', label: 'Dashboard', icon: 'dashboard', end: true },
    { to: '/teacher/monitor', label: 'Live Monitor', icon: 'monitor' },
    { to: '/teacher/exams', label: 'Exams', icon: 'exams' },
    { to: '/teacher/exams/new', label: 'Create Exam', icon: 'create' },
    { to: '/teacher/results', label: 'Results', icon: 'results' },
    { to: '/teacher/analytics', label: 'Analytics', icon: 'analytics' },
    { to: '/teacher/proctoring', label: 'Proctoring', icon: 'proctoring' },
  ],
  student: [
    { to: '/student', label: 'Dashboard', icon: 'dashboard', end: true },
    { to: '/student/exams', label: 'My Exams', icon: 'mine' },
    { to: '/student/results', label: 'My Results', icon: 'results' },
    { to: '/student/profile', label: 'Profile', icon: 'profile' },
  ],
}

function NotificationsBell() {
  const [open, setOpen] = useState(false)
  const [unread, setUnread] = useState(0)
  const [items, setItems] = useState([])
  const openRef = useRef(open)
  const navigate = useNavigate()
  openRef.current = open

  function refreshCount() {
    api('/notifications/unread-count')
      .then((c) => setUnread(c.unread ?? 0))
      .catch(() => {})
  }

  useEffect(() => {
    refreshCount()
    const t = setInterval(refreshCount, 30000)
    return () => clearInterval(t)
  }, [])

  async function toggle() {
    const next = !openRef.current
    setOpen(next)
    if (next) {
      try {
        const list = await api('/notifications')
        setItems(list || [])
        refreshCount()
      } catch {
        setItems([])
      }
    }
  }

  async function markRead(id) {
    try {
      await api(`/notifications/${id}/read`, { method: 'POST' })
      setItems((xs) => xs.map((x) => (x.id === id ? { ...x, read: true } : x)))
      refreshCount()
    } catch {
      /* ignore */
    }
  }

  async function markAll() {
    try {
      await api('/notifications/read-all', { method: 'POST' })
      setItems((xs) => xs.map((x) => ({ ...x, read: true })))
      setUnread(0)
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="bell-wrap">
      <button className="bell-btn" onClick={toggle} aria-label="Notifications">
        <span className="bell-icon">🔔</span>
        {unread > 0 && <span className="bell-dot">{unread > 99 ? '99+' : unread}</span>}
      </button>
      {open && (
        <>
          <div className="bell-backdrop" onClick={() => setOpen(false)} />
          <div className="bell-menu">
            <div className="bell-head">
              <strong>Notifications</strong>
              {unread > 0 && (
                <button className="btn btn-ghost btn-sm" onClick={markAll}>Mark all read</button>
              )}
            </div>
            <div className="bell-body">
              {items.length ? (
                items.map((n) => (
                  <button
                    key={n.id}
                    className={`bell-item ${n.read ? '' : 'unread'}`}
                    onClick={() => {
                      if (!n.read) markRead(n.id)
                      setOpen(false)
                      if (n.link) navigate(n.link)
                    }}
                  >
                    <div className="bell-title">
                      {!n.read && <i className="bell-unread-dot" />}
                      <strong>{n.title}</strong>
                    </div>
                    {n.body && <div className="bell-body-text">{n.body}</div>}
                    <div className="bell-time muted">{timeAgo(n.created_at)}</div>
                  </button>
                ))
              ) : (
                <div className="bell-empty">No notifications yet.</div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export function Layout({ role }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  const links = NAV[role] || []

  return (
    <>
      <CommandBackground />
      <div className="shell">
        <aside className="sidebar">
          <div className="brand">
            <span className="brand-mark">P</span>
            <div>
              <strong>PROCTIFY</strong>
              <small>AI Examination System</small>
            </div>
          </div>
          <nav className="nav">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}
              >
                <span className="nav-ico" aria-hidden="true">{ICONS[l.icon] || '·'}</span>
                {l.label}
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-foot">
            <span className="pill">{role}</span>
          </div>
        </aside>
        <div className="main">
          <header className="topbar">
            <div className="topbar-title">COMMAND CENTER</div>
            <div className="topbar-user">
              <NotificationsBell />
              <span className="avatar">{user?.full_name?.[0]?.toUpperCase()}</span>
              <div className="topbar-identity">
                <strong>{user?.full_name}</strong>
                <small>@{user?.username}</small>
              </div>
              <button className="btn btn-ghost" onClick={handleLogout}>
                Logout
              </button>
            </div>
          </header>
          <main className="content page-enter">
            <Outlet />
          </main>
        </div>
      </div>
    </>
  )
}