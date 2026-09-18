import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const NAV = {
  admin: [
    { to: '/admin', label: 'Dashboard', end: true },
    { to: '/admin/users', label: 'Users' },
    { to: '/admin/students', label: 'Students' },
    { to: '/admin/enrollment', label: 'Bulk Enrollment' },
    { to: '/admin/classes', label: 'Classes / Batches' },
  ],
  teacher: [
    { to: '/teacher', label: 'Dashboard', end: true },
    { to: '/teacher/exams', label: 'Exams' },
    { to: '/teacher/exams/new', label: 'Create Exam' },
    { to: '/teacher/proctoring', label: 'Proctoring' },
  ],
  student: [
    { to: '/student', label: 'Dashboard', end: true },
    { to: '/student/exams', label: 'My Exams' },
    { to: '/student/profile', label: 'Profile' },
  ],
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
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">P</span>
          <div>
            <strong>PROCTIFY</strong>
            <small>Examination System</small>
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
          <div className="topbar-title">PROCTIFY</div>
          <div className="topbar-user">
            <span className="avatar">{user?.full_name?.[0]?.toUpperCase()}</span>
            <div className="topbar-identity">
              <strong>{user?.full_name}</strong>
              <small>{user?.email}</small>
            </div>
            <button className="btn btn-ghost" onClick={handleLogout}>
              Logout
            </button>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}