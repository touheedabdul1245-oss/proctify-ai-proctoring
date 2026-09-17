export const API_BASE = '/api'

const TOKEN_KEY = 'proctify_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail || {}))
    this.status = status
    this.detail = detail
  }
}

async function handle(resp) {
  const text = await resp.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }
  if (!resp.ok) {
    throw new ApiError(resp.status, data?.detail || data || `HTTP ${resp.status}`)
  }
  return data
}

export async function api(path, { method = 'GET', body, token = getToken(), isForm = false } = {}) {
  const headers = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  let payload = body
  if (body !== undefined && !isForm) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: payload !== undefined ? payload : undefined,
  })
  return handle(resp)
}

export function errorMessage(err) {
  if (err instanceof ApiError) {
    const d = err.detail
    if (Array.isArray(d) && d[0]?.msg) return d.map((x) => x.msg).join('; ')
    if (typeof d === 'string') return d
    return JSON.stringify(d)
  }
  return err?.message || 'Request failed'
}