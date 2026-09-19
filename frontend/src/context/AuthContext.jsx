import { createContext, useContext, useEffect, useState } from 'react'
import { api, getToken, setToken } from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const token = getToken()
    if (!token) {
      setLoading(false)
      return
    }
    api('/auth/me')
      .then((me) => {
        setUser(me)
        setLoading(false)
      })
      .catch(() => {
        setToken(null)
        setUser(null)
        setLoading(false)
      })
  }, [])

  async function login(username, password) {
    setError(null)
    try {
      const res = await api('/auth/login', {
        method: 'POST',
        body: { username, password },
        token: null,
      })
      setToken(res.access_token)
      setUser(res.user)
      return res.user
    } catch (err) {
      setError(err)
      throw err
    }
  }

  function logout() {
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, error, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}