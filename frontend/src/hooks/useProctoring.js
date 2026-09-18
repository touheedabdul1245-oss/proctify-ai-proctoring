import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'

const DEFAULT_POLL = 5000
const RATE_LIMIT_BACKOFF = 6000
const FRAME_MAX = { width: 640, height: 360 }

function noCameraObservation() {
  return {
    camera_available: false,
    objects: [],
    face: { available: false, face_count: 0, faces: [] },
    head_pose: {},
    audio: { available: true, speech_detected: false },
  }
}

/**
 * Student live-proctoring feed.
 *
 * Polls the per-session config, acquires the user camera once, then posts
 * small JPEG frames on the server-advertised cadence. Honours the server's
 * 429 rate limiter with a fixed back-off, and degrades gracefully to an
 * honest "no camera" observation when the device is absent/denied so the
 * engine still sees the coverage gap (never silent).
 *
 * status: idle | active | no-camera | off | done | error
 */
export function useProctoring(sessionToken, { paused = false } = {}) {
  const [status, setStatus] = useState('idle')
  const [pollInterval, setPollInterval] = useState(DEFAULT_POLL / 1000)

  const pollRef = useRef(pollInterval)
  const pausedRef = useRef(paused)
  const tokenRef = useRef(sessionToken)
  const stoppedRef = useRef(true)
  const busyRef = useRef(false)
  const streamRef = useRef(null)
  const videoRef = useRef(null)

  pollRef.current = pollInterval
  pausedRef.current = paused
  tokenRef.current = sessionToken

  const stop = useCallback(() => {
    stoppedRef.current = true
    streamRef.current?.getTracks?.().forEach((t) => t.stop())
    streamRef.current = null
    videoRef.current = null
  }, [])

  const postFrame = useCallback(async (observation) => {
    const token = tokenRef.current
    if (!token || stoppedRef.current || busyRef.current) return
    busyRef.current = true
    try {
      await api(`/student/sessions/${token}/proctoring`, {
        method: 'POST',
        body: { session_token: token, observation },
      })
    } catch (e) {
      if (e?.status === 409) {
        stoppedRef.current = true
        setStatus('done')
        stop()
      } else if (e?.status === 429) {
        return await new Promise((r) => setTimeout(r, RATE_LIMIT_BACKOFF))
      }
    } finally {
      busyRef.current = false
    }
  }, [stop])

  const queueNext = useCallback(() => {
    if (stoppedRef.current) return
    const interval = Math.max(Math.round(pollRef.current * 1000), 3000)
    setTimeout(tick, interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const tick = useCallback(async () => {
    if (stoppedRef.current || pausedRef.current) return
    const token = tokenRef.current
    if (!token) return

    if (streamRef.current?.active && videoRef.current) {
      try {
        const canvas = document.createElement('canvas')
        const v = videoRef.current
        let w = v.videoWidth || FRAME_MAX.width
        let h = v.videoHeight || FRAME_MAX.height
        const scale = Math.min(1, FRAME_MAX.width / w, FRAME_MAX.height / h)
        w = Math.max(2, Math.round(w * scale))
        h = Math.max(2, Math.round(h * scale))
        canvas.width = w
        canvas.height = h
        canvas.getContext('2d').drawImage(v, 0, 0, w, h)
        const frame_data_url = canvas.toDataURL('image/jpeg', 0.62)
        const r = postFrame({ camera_available: true, frame_data_url })
        if (r) await r
      } catch {
        /* transient frame encode error — skip this tick */
      }
    } else {
      await postFrame(noCameraObservation())
    }
    if (!stoppedRef.current) queueNext()
  }, [postFrame, queueNext])

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const start = useCallback(async () => {
    stoppedRef.current = false
    setStatus('active')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 960 }, height: { ideal: 540 } },
        audio: false,
      })
      streamRef.current = stream
      videoRef.current = document.createElement('video')
      videoRef.current.srcObject = stream
      videoRef.current.playsInline = true
      videoRef.current.muted = true
      await videoRef.current.play()
      if (stoppedRef.current) {
        streamRef.current?.getTracks?.().forEach((t) => t.stop())
        streamRef.current = null
        return
      }
    } catch {
      if (!stoppedRef.current) setStatus('no-camera')
    }
    tick()
  }, [tick])

  // --- config + start ---
  useEffect(() => {
    if (!sessionToken) return
    let alive = true
    stoppedRef.current = false
    setStatus('idle')
    ;(async () => {
      try {
        const cfg = await api(`/student/sessions/${sessionToken}/proctoring/config`)
        if (!alive) return
        setPollInterval(cfg.poll_interval_seconds || DEFAULT_POLL / 1000)
        if (!cfg.enabled) {
          setStatus('off')
          stop()
          return
        }
      } catch {
        if (alive) setStatus('error')
        return
      }
      if (alive && !stoppedRef.current) start()
    })()
    return () => {
      alive = false
      stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionToken, start, stop])

  return { status, pollInterval }
}