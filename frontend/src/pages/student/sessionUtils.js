import { api } from '../../api'

export function getSessionForExam(examId) {
  return api(`/student/exams/${examId}/session`)
}

export function createSession(examId) {
  return api(`/student/exams/${examId}/session`, { method: 'POST' })
}

export function redirectForStatus(status, token, navigate) {
  if (status === 'ACTIVE') navigate(`/student/exam/${token}`)
  else if (status === 'SUBMITTED' || status === 'EXPIRED' || status === 'TERMINATED') navigate(`/student/result/${token}`)
}