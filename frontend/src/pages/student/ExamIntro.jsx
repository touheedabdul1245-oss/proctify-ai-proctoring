import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { api } from '../../api'
import { PageHeader, Card, Badge, Loading, ErrorBox, fmtDate } from '../../components/Ui'
import { createSession, getSessionForExam, redirectForStatus } from './sessionUtils'

const READINESS_MARK = {
  identity_verified: 'Identity confirmed',
  camera_checked: 'Camera check passed',
  microphone_checked: 'Microphone check passed',
  environment_ready: 'Environment ready',
}

async function stopStream(stream) {
  stream?.getTracks().forEach((t) => t.stop())
}

async function requestCamera() {
  return navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 } }, audio: false })
}

async function requestMic() {
  return navigator.mediaDevices.getUserMedia({ video: false, audio: true })
}

function captureStill(video) {
  const canvas = document.createElement('canvas')
  canvas.width = video.videoWidth || 320
  canvas.height = video.videoHeight || 240
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', 0.82)
}

function Step({ done, error, title, children }) {
  return (
    <div className={`wizard-step ${done ? 'done' : ''}`}>
      <div className="wizard-step-head">
        <span className={`wizard-dot ${done ? 'ok' : ''}`}>{done ? '✓' : '•'}</span>
        <strong>{title}</strong>
        {done && <span className="wizard-done-label">{READINESS_MARK[title] || 'done'}</span>}
      </div>
      <div className="wizard-step-body">{children}</div>
      {error && <div className="error-box">{error}</div>}
    </div>
  )
}

export default function ExamIntro() {
  const params = useParams()
  const examId = params.id
  const navigate = useNavigate()
  const [exam, setExam] = useState(null)
  const [profile, setProfile] = useState(null)
  const [state, setState] = useState(null) // session state endpoint
  const [session, setSession] = useState(null) // full session GET (readiness)
  const [err, setErr] = useState(null)
  const [creating, setCreating] = useState(false)
  const loaded = useRef(false)

  const [rd, setRd] = useState({ identity_verified: false, camera_checked: false, microphone_checked: false, environment_ready: false })
  const [rdErr, setRdErr] = useState(null)

  const [identityOk, setIdentityOk] = useState(false)
  const [photoData, setPhotoData] = useState(null)
  const camRef = useRef(null)
  const camStreamRef = useRef(null)
  const [camBusy, setCamBusy] = useState(false)
  const [camPreview, setCamPreview] = useState(false)
  const [micBusy, setMicBusy] = useState(false)
  const [micLevel, setMicLevel] = useState(0)
  const [micResult, setMicResult] = useState(null) // {ok:boolean}
  const [env, setEnv] = useState(null) // {ok:boolean}
  const [starting, setStarting] = useState(false)

  useEffect(() => {
    if (loaded.current) return
    loaded.current = true
    ;(async () => {
      try {
        const [det, prof, st] = await Promise.all([
          api(`/student/exams/${examId}`),
          api('/profile'),
          getSessionForExam(examId),
        ])
        setExam(det)
        setProfile(prof)
        setState(st)
        if (!st.session_token) {
          setCreating(true)
          const created = await createSession(examId)
          setState({ session_token: created.session_token, status: created.status })
          const full = await api(`/student/sessions/${created.session_token}`)
          setSession(full)
          setRd({
            identity_verified: full.readiness?.identity_verified,
            camera_checked: full.readiness?.camera_checked,
            microphone_checked: full.readiness?.microphone_checked,
            environment_ready: full.readiness?.environment_ready,
          })
          redirectForStatus(full.status, full.session_token, navigate)
          setCreating(false)
        } else {
          const full = await api(`/student/sessions/${st.session_token}`)
          setSession(full)
          setRd({
            identity_verified: full.readiness?.identity_verified,
            camera_checked: full.readiness?.camera_checked,
            microphone_checked: full.readiness?.microphone_checked,
            environment_ready: full.readiness?.environment_ready,
          })
          redirectForStatus(full.status, full.session_token, navigate)
        }
      } catch (e) {
        setErr(e?.message || 'Failed to prepare session')
      }
    })()
    return () => stopStream(camStreamRef.current)
  }, [examId, navigate])

  async function postReadiness(patch) {
    setRdErr(null)
    try {
      const res = await api(`/student/sessions/${state.session_token}/readiness`, {
        method: 'POST',
        body: { ...patch, identity_photo_data: photoData || undefined },
      })
      setRd((prev) => ({
        identity_verified: res.identity_verified ?? prev.identity_verified,
        camera_checked: res.camera_checked ?? prev.camera_checked,
        microphone_checked: res.microphone_checked ?? prev.microphone_checked,
        environment_ready: res.environment_ready ?? prev.environment_ready,
      }))
      return res
    } catch (e) {
      setRdErr(e?.message || 'Could not save readiness')
      return null
    }
  }

  async function confirmIdentity() {
    await postReadiness({ identity_verified: true })
  }

  async function runCameraCheck() {
    setCamBusy(true)
    setRdErr(null)
    setCamPreview(false)
    try {
      const stream = await requestCamera()
      camStreamRef.current = stream
      setCamPreview(true)
    } catch (e) {
      console.error('camera-check-failed', e?.name, e?.message)
      setCamPreview(false)
      await postReadiness({ camera_checked: false, camera_error: 'Camera permission denied or unavailable' })
    } finally {
      setCamBusy(false)
    }
  }

  useEffect(() => {
    const el = camRef.current
    if (camPreview && camStreamRef.current && el) {
      el.srcObject = camStreamRef.current
      el.play().catch(() => {})
    }
  }, [camPreview])

  async function captureAndConfirmCamera() {
    if (camRef.current && camStreamRef.current) {
      setPhotoData(captureStill(camRef.current))
    }
    await stopStream(camStreamRef.current)
    camStreamRef.current = null
    setCamPreview(false)
    await postReadiness({ camera_checked: true })
  }

  async function skipCamera() {
    await stopStream(camStreamRef.current)
    camStreamRef.current = null
    setCamPreview(false)
  }

  async function runMicCheck() {
    setMicBusy(true)
    setMicResult(null)
    setRdErr(null)
    try {
      const stream = await requestMic()
      const ctx = new (window.AudioContext || window.webkitAudioContext)()
      const src = ctx.createMediaStreamSource(stream)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 256
      src.connect(analyser)
      const data = new Uint8Array(analyser.frequencyBinCount)
      let peak = 0
      await new Promise((resolve) => {
        const t0 = Date.now()
        const tick = () => {
          analyser.getByteFrequencyData(data)
          const sum = data.reduce((a, b) => a + b, 0) / data.length
          peak = Math.max(peak, sum)
          setMicLevel(sum)
          if (Date.now() - t0 < 2000) setTimeout(tick, 100)
          else resolve()
        }
        tick()
      })
      src.disconnect()
      ctx.close()
      await stopStream(stream)
      const ok = peak > 1
      setMicResult({ ok })
      setMicLevel(0)
      await postReadiness({ microphone_checked: ok, microphone_error: ok ? undefined : 'No audio detected' })
    } catch (e) {
      setMicResult({ ok: false })
      await postReadiness({ microphone_checked: false, microphone_error: 'Microphone permission denied or unavailable' })
    } finally {
      setMicBusy(false)
    }
  }

  function runEnvCheck() {
    const online = navigator.onLine !== false
    const envOk = online
    setEnv({ ok: envOk, online, userAgent: navigator.userAgent })
    postReadiness({ environment_ready: envOk })
  }

  async function startExam() {
    setStarting(true)
    setRdErr(null)
    try {
      const res = await api(`/student/sessions/${state.session_token}/start`, { method: 'POST' })
      navigate(`/student/exam/${res.session_token}`)
    } catch (e) {
      setRdErr(e?.message || 'Could not start exam')
      setStarting(false)
    }
  }

  if (err) {
    return (
      <div>
        <PageHeader title="Exam" />
        <Card>
          <ErrorBox error={err} />
          <Link className="btn btn-secondary" to="/student/exams">
            Back to exams
          </Link>
        </Card>
      </div>
    )
  }

  if (!exam || !profile || (creating && !session)) {
    return <Loading />
  }

  const readyAll = rd.identity_verified && rd.camera_checked && rd.microphone_checked && rd.environment_ready

  return (
    <div>
      <PageHeader title={exam.title} subtitle="Pre-exam setup — complete all checks before starting" />
      <Card>
        <div className="summary-strip">
          <div className="summary-item"><strong>{exam.duration_minutes}</strong> minutes</div>
          <div className="summary-item"><strong>{exam.total_marks}</strong> marks</div>
          <div className="summary-item"><strong>{exam.question_count}</strong> questions</div>
          <div className="summary-item"><strong><Badge status={exam.status} /></strong></div>
        </div>
        {exam.description && <p>{exam.description}</p>}
        <table className="table" style={{ maxWidth: 560 }}>
          <tbody>
            <tr><td className="muted" width="150">Scheduled window</td><td>{fmtDate(exam.scheduled_start)} → {fmtDate(exam.scheduled_end)}</td></tr>
            <tr><td className="muted">Exam code</td><td className="mono">{exam.exam_code}</td></tr>
          </tbody>
        </table>
      </Card>

      <Card title="Readiness checks">
        <p className="muted" style={{ marginTop: 0 }}>
          You must pass every check below before the timer can start. The camera and microphone are used only
          during the pre-exam setup in Stage 2.
        </p>

        <Step title="identity" done={rd.identity_verified}>
          <table className="table" style={{ maxWidth: 560 }}>
            <tbody>
              <tr><td className="muted" width="150">Name</td><td>{profile.user?.full_name}</td></tr>
              <tr><td className="muted">Username</td><td>@{profile.user?.username}</td></tr>
              <tr><td className="muted">Student ID</td><td>{profile.student_id || '—'}</td></tr>
              <tr><td className="muted">Email</td><td>{profile.user?.email}</td></tr>
            </tbody>
          </table>
          <label className="field" style={{ marginTop: 12 }}>
            <span className="field-label">
              <input
                type="checkbox"
                style={{ width: 'auto', marginRight: 8 }}
                checked={identityOk}
                onChange={(e) => setIdentityOk(e.target.checked)}
              />
              I confirm that I am {profile.user?.full_name} and I will take this exam myself without external help.
            </span>
          </label>
          {!rd.identity_verified && (
            <button className="btn btn-primary" disabled={!identityOk} onClick={confirmIdentity}>
              Confirm identity
            </button>
          )}
        </Step>

        <Step title="camera" done={rd.camera_checked}>
          {camPreview ? (
            <div>
              <video
                ref={camRef}
                autoPlay
                muted
                playsInline
                className="cam-preview"
              />
              <div className="segment-row">
                <button className="btn btn-primary" onClick={captureAndConfirmCamera}>
                  Capture photo &amp; confirm camera
                </button>
                <button className="btn btn-ghost" onClick={skipCamera}>Skip photo</button>
              </div>
              <p className="muted" style={{ marginBottom: 0 }}>
                A still of you is captured and stored as your identity snapshot for this session.
              </p>
            </div>
          ) : (
            <div>
              <p style={{ marginTop: 0 }}>We need to verify your camera works before the exam.</p>
              <button className="btn btn-primary" disabled={camBusy} onClick={runCameraCheck}>
                {camBusy ? 'Checking…' : 'Check camera'}
              </button>
            </div>
          )}
        </Step>

        <Step title="microphone" done={rd.microphone_checked}>
          <p style={{ marginTop: 0 }}>
            Speak or make a sound for a few seconds so we can confirm your microphone is working.
          </p>
          <button className="btn btn-primary" disabled={micBusy} onClick={runMicCheck}>
            {micBusy ? 'Listening…' : 'Check microphone'}
          </button>
          {micBusy && (
            <div className="mic-meter">
              <div className="mic-level" style={{ width: `${Math.min(100, (micLevel / 255) * 100)}%` }} />
            </div>
          )}
          {micResult && !micResult.ok && (
            <p className="error-box" style={{ marginBottom: 0 }}>No audio detected — microphone may be muted or blocked.</p>
          )}
        </Step>

        <Step title="environment_ready" done={rd.environment_ready}>
          <p style={{ marginTop: 0 }}>
            Confirm your browser and network are ready for a stable connection throughout the exam.
          </p>
          <button className="btn btn-primary" onClick={runEnvCheck}>
            Run environment check
          </button>
          {env && (
            <p className="muted" style={{ marginBottom: 0 }}>
              Network: {env.online ? 'online ✓' : 'offline ✗'} — {env.userAgent.split(')')[0]}
            </p>
          )}
        </Step>

        {rdErr && <ErrorBox error={rdErr} />}

        {readyAll && (
          <div className="success-box" style={{ marginTop: 6 }}>
            All checks passed. You're ready to begin.
          </div>
        )}

        <div className="form-actions" style={{ marginTop: 14 }}>
          <Link className="btn btn-ghost" to="/student/exams">Cancel</Link>
          <button className="btn btn-primary" disabled={!readyAll || starting} onClick={startExam}>
            {starting ? 'Starting…' : 'Start exam'}
          </button>
        </div>
      </Card>
    </div>
  )
}