import { Route, Routes, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import { Layout } from './components/Layout'
import Login from './pages/Login'
import AdminDashboard from './pages/admin/AdminDashboard'
import Users from './pages/admin/Users'
import Students from './pages/admin/Students'
import BulkEnrollment from './pages/admin/BulkEnrollment'
import Classes from './pages/admin/Classes'
import TeacherDashboard from './pages/teacher/TeacherDashboard'
import Exams from './pages/teacher/Exams'
import ExamEditor from './pages/teacher/ExamEditor'
import StudentDashboard from './pages/student/StudentDashboard'
import Profile from './pages/student/Profile'
import AssignedExams from './pages/student/AssignedExams'

function Protected({ roles, children }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="page-loading">Loading…</div>
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />
  if (roles && !roles.includes(user.role)) {
    return <Navigate to={`/${user.role}`} replace />
  }
  return children
}

function Home() {
  const { user, loading } = useAuth()
  if (loading) return <div className="page-loading">Loading…</div>
  const dest = user ? `/${user.role}` : '/login'
  return <Navigate to={dest} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Home />} />

      <Route
        path="/admin"
        element={
          <Protected roles={['admin']}>
            <Layout role="admin" />
          </Protected>
        }
      >
        <Route index element={<AdminDashboard />} />
        <Route path="users" element={<Users />} />
        <Route path="students" element={<Students />} />
        <Route path="enrollment" element={<BulkEnrollment />} />
        <Route path="classes" element={<Classes />} />
      </Route>

      <Route
        path="/teacher"
        element={
          <Protected roles={['teacher', 'admin']}>
            <Layout role="teacher" />
          </Protected>
        }
      >
        <Route index element={<TeacherDashboard />} />
        <Route path="exams" element={<Exams />} />
        <Route path="exams/new" element={<ExamEditor />} />
        <Route path="exams/:id" element={<ExamEditor />} />
      </Route>

      <Route
        path="/student"
        element={
          <Protected roles={['student']}>
            <Layout role="student" />
          </Protected>
        }
      >
        <Route index element={<StudentDashboard />} />
        <Route path="profile" element={<Profile />} />
        <Route path="exams" element={<AssignedExams />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}