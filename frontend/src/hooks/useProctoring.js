import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'

const DEFAULT_POLL = 5000
const RATE_LIMIT_BACKOFF = 6000
const FRAME_MAX = { width: 640, height: 360 }
const PCM_TARGET_RATE = 16000
const PCM_SECONDS = 1.0

function noCameraObservation(audio) {
  return {
    camera_available: false,
    objects: [],
    face: { available: false, face_count: 0, faces: [] },
    head_pose: {},
    audio: audio || { available: false },
  }
}

function bytesToBase64(buffer) {
  let binary = ''
  const bytes = new Uint8Array(buffer)
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk))
  }
  return btoa(binary)
}

function buildAudioPayload(ring, sourceRate, micOn) {
  if (!micOn || !ring || ring.len < Math.floor(sourceRate * 0.3)) {
    return { available: !!micOn }
  }
  const take = Math.min(Math.floor(sourceRate * PCM_SECONDS), ring.len)
  const outLen = Math.max(1, Math.floor((take * PCM_TARGET_RATE) / sourceRate))
  const out = new Float32Array(outLen)
  const factor = sourceRate / PCM_TARGET_RATE
  let o = 0
  for (let i = 0; i < take && o < outLen; i += 1) {
    if (i % Math.floor(factor) === 0) {
      const srcIndex = ring.len - take + i
      out[o++] = ring.buf[(ring.head + srcIndex) % ring.buf.length]
    }
  }
  const pcm = new Int16Array(outLen)
  for (let i = 0; i < outLen; i += 1) {
    const s = Math.max(-1, Math.min(1, out[i]))
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return {
    available: true,
    sample_rate: PCM_TARGET_RATE,
    pcm_data: bytesToBase64(pcm.buffer),
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
 * Microphone: requested SEPARATELY from the camera so a denied mic never
 * kills the video feed. When granted, ~1s of 16 kHz Int16 mono PCM is
 * base64-encoded onto each observation; the server analyzes it with the real
 * audio_service. When denied/absent, `audio: { available: false }` is sent so
 * the engine honestly reports AUDIO_UNAVAILABLE.
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
  const audioCtxRef = useRef(null)
  const audioRingRef = useRef(null)
  const micRef = useRef(false)

  pollRef.current = pollInterval
  pausedRef.current = paused
  tokenRef.current = sessionToken

  const stop = useCallback(() => {
    stoppedRef.current = true
    streamRef.current?.getTracks?.().forEach((t) => t.stop())
    streamRef.current = null
    videoRef.current = null
    if (audioCtxRef.current) {
      try {
        audioCtxRef.current.close()
      } catch {
        /* already closed */
      }
      audioCtxRef.current = null
    }
    audioRingRef.current = null
    micRef.current = false
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
    const audioPayload = buildAudioPayload(
      audioRingRef.current,
      audioCtxRef.current?.sampleRate || PCM_TARGET_RATE,
      micRef.current,
    )

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
        const r = postFrame({ camera_available: true, frame_data_url, audio: audioPayload })
        if (r) await r
      } catch {
        /* transient frame encode error — skip this tick */
      }
    } else {
      await postFrame(noCameraObservation(audioPayload))
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

      // Microphone: requested SEPARATELY so a denied mic never blocks the
      // camera feed. When granted, a ScriptProcessor ring holds ~1.3s of raw
      // samples; buildAudioPayload downsamples + base64s ~1s of Int16 PCM.
      try {
        const micStream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
        })
        const Ctx = window.AudioContext || window.webkitAudioContext
        if (Ctx && micStream.getAudioTracks().length > 0) {
          micStream.getAudioTracks().forEach((t) => stream.addTrack(t))
          const ctx = new Ctx()
          const ring = {
            buf: new Float32Array(Math.ceil(ctx.sampleRate * 1.3)),
            head: 0,
            len: 0,
          }
          audioRingRef.current = ring
          const source = ctx.createMediaStreamSource(micStream)
          const processor = ctx.createScriptProcessor(4096, 1, 1)
          processor.onaudioprocess = (e) => {
            const data = e.inputBuffer.getChannelData(0)
            for (let i = 0; i < data.length; i += 1) {
              ring.buf[ring.head] = data[i]
              ring.head = (ring.head + 1) % ring.buf.length
              if (ring.len < ring.buf.length) ring.len += 1
            }
          }
          const silence = ctx.createGain()
          silence.gain.value = 0
          source.connect(processor)
          processor.connect(silence)
          silence.connect(ctx.destination)
          audioCtxRef.current = ctx
          micRef.current = true
        } else {
          micStream.getTracks().forEach((t) => t.stop())
          micRef.current = false
        }
      } catch {
        micRef.current = false
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