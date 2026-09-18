import test from 'node:test'
import assert from 'node:assert/strict'

import {
  RISK_ORDER,
  MONITOR_LEVELS,
  normalizeLevel,
  normalizeStatus,
  riskClass,
  monitorStatusClass,
  reviewStatusClass,
  filterMonitorRows,
  summarize,
  countRisk,
  timeAgo,
  riskHistoryBars,
  REVIEW_ACTIONS,
  formatIndex,
  shortToken,
  eventLabel,
} from './monitorUtils.js'

const ROWS = [
  {
    id: 1,
    student_name: 'Alice Alpha',
    student_email: 'alice@test.dev',
    exam_code: 'E1',
    exam_title: 'Exam One',
    session_token: 'TOKEN-AAA',
    student_id: 101,
    risk_level: 'HIGH',
    monitor_status: 'LIVE',
    pending_incidents: 2,
    incident_count: 3,
    evidence_count: 4,
    event_count_24h: 9,
    camera_available: true,
    audio_available: false,
    last_activity_at: '2026-09-18T10:00:00Z',
  },
  {
    id: 2,
    student_name: 'Bob Beta',
    student_email: 'bob@test.dev',
    exam_code: 'E2',
    exam_title: 'Exam Two',
    session_token: 'TOKEN-BBB',
    student_id: 202,
    risk_level: 'NORMAL',
    monitor_status: 'IDLE',
    pending_incidents: 0,
  },
]

test('normalizeLevel maps LOW/NORMAL and unknown to NORMAL; keeps band levels', () => {
  assert.equal(normalizeLevel('high'), 'HIGH')
  assert.equal(normalizeLevel('LOW'), 'LOW')
  assert.equal(normalizeLevel('weird'), 'NORMAL')
  assert.equal(normalizeLevel(undefined), 'NORMAL')
})

test('normalizeStatus coerces unknown to IDLE', () => {
  assert.equal(normalizeStatus('live'), 'LIVE')
  assert.equal(normalizeStatus('bogus'), 'IDLE')
})

test('riskClass and monitorStatusClass map to stable css classes', () => {
  assert.equal(riskClass('HIGH'), 'risk-pill risk-high')
  assert.equal(riskClass('attention'), 'risk-pill risk-attention')
  assert.equal(monitorStatusClass('LIVE'), 'mon-status mon-live')
  assert.equal(reviewStatusClass('CONFIRMED'), 'badge badge-review-confirmed')
})

test('filterMonitorRows searches name/email/exam/token and combined filters', () => {
  assert.equal(filterMonitorRows(ROWS, { q: 'alice' }).length, 1)
  assert.equal(filterMonitorRows(ROWS, { q: 'E2' }).length, 1)
  assert.equal(filterMonitorRows(ROWS, { q: 'token-BBB' }).length, 1)
  assert.equal(filterMonitorRows(ROWS, { risk: 'HIGH' }).length, 1)
  assert.equal(filterMonitorRows(ROWS, { status: 'IDLE' }).length, 1)
  assert.equal(filterMonitorRows(ROWS, { risk: 'HIGH', status: 'IDLE' }).length, 0)
  assert.equal(filterMonitorRows(ROWS, { q: 'zzz' }).length, 0)
  assert.equal(filterMonitorRows(ROWS, { q: '', risk: 'ALL', status: 'ALL' }).length, 2)
})

test('summarize totals live/pending/risk counts from the grid', () => {
  const s = summarize(ROWS)
  assert.equal(s.total, 2)
  assert.equal(s.live, 1)
  assert.equal(s.pending, 2)
  assert.equal(s.byRisk.HIGH, 1)
  assert.equal(s.byRisk.NORMAL, 1)
  assert.equal(s.byRisk.ATTENTION, 0)
  assert.equal(s.byRisk.ELEVATED, 0)
})

test('countRisk tolerates malformed levels', () => {
  const c = countRisk([{ risk_level: 'ELEVATED' }, { risk_level: '??' }, {}])
  assert.equal(c.ELEVATED, 1)
  assert.equal(c.NORMAL, 2)
  assert.deepEqual(Object.keys(c).sort(), [...MONITOR_LEVELS].sort())
})

test('timeAgo renders compact relative durations', () => {
  const now = Date.now()
  assert.equal(timeAgo(null, now), '—')
  assert.equal(timeAgo(new Date(now - 3000).toISOString(), now), 'just now')
  assert.equal(timeAgo(new Date(now - 30000).toISOString(), now), '30s ago')
  assert.equal(timeAgo(new Date(now - 2 * 60000).toISOString(), now), '2m ago')
  assert.equal(timeAgo(new Date(now - 3 * 3600000).toISOString(), now), '3h ago')
  assert.equal(timeAgo(new Date(now - 2 * 86400000).toISOString(), now), '2d ago')
})

test('riskHistoryBars sorts chronologically, caps length, uses index_value', () => {
  const rows = [
    { level: 'ELEVATED', index_value: 0.62, recorded_at: '2026-09-18T09:00:00Z' },
    { level: 'NORMAL', index_value: 0.1, recorded_at: '2026-09-18T08:00:00Z' },
    { level: 'HIGH', index_value: 0.9, recorded_at: '2026-09-18T10:00:00Z' },
  ]
  const bars = riskHistoryBars(rows, { max: 2 })
  assert.deepEqual(bars.map((b) => b.level), ['ELEVATED', 'HIGH'])
  assert.equal(bars[1].value, 0.9)
})

test('REVIEW_ACTIONS exposes the teacher verdict vocabulary', () => {
  assert.equal(REVIEW_ACTIONS.CONFIRM.next, 'CONFIRMED')
  assert.equal(REVIEW_ACTIONS.DISMISS.next, 'DISMISSED')
  assert.equal(REVIEW_ACTIONS.RESOLVE.next, 'RESOLVED')
  assert.deepEqual(Object.keys(RISK_ORDER), ['NORMAL', 'LOW', 'ATTENTION', 'ELEVATED', 'HIGH'])
})

test('formatting helpers are deterministic', () => {
  assert.equal(formatIndex(0.628), '0.628')
  assert.equal(formatIndex(undefined), '—')
  assert.equal(shortToken('TOKEN-AAA', 6), 'TOKEN-')
  assert.equal(shortToken('', 8), '')
  assert.equal(eventLabel({ event_type: 'OBJECT_PHONE' }), 'object phone')
  assert.equal(eventLabel({}), '—')
})