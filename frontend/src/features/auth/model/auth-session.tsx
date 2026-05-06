/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { fetchCurrentUser, type AuthSession, type User } from '@/entities/user'
import { ApiError, apiRequest, isAuthError } from '@/shared/api'

const tokenStorageKey = 'trade-helper.access-token'

type AuthStatus = 'anonymous' | 'authenticated' | 'restore_failed' | 'restoring'

type AuthContextValue = {
  status: AuthStatus
  token: string | null
  user: User | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
  retryRestore: () => void
  handleAuthError: (error: unknown) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthSessionProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => readStoredToken())
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<AuthStatus>(token ? 'restoring' : 'anonymous')
  const [restoreKey, setRestoreKey] = useState(0)

  const clearSession = useCallback(() => {
    sessionStorage.removeItem(tokenStorageKey)
    localStorage.removeItem(tokenStorageKey)
    setToken(null)
    setUser(null)
    setStatus('anonymous')
  }, [])

  const storeSession = useCallback((session: AuthSession) => {
    sessionStorage.setItem(tokenStorageKey, session.access_token)
    localStorage.removeItem(tokenStorageKey)
    setToken(session.access_token)
    setUser(session.user)
    setStatus('authenticated')
  }, [])

  useEffect(() => {
    if (!token || status === 'authenticated') {
      return
    }

    const controller = new AbortController()
    fetchCurrentUser(token, controller.signal)
      .then((currentUser) => {
        setUser(currentUser)
        setStatus('authenticated')
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return
        }
        if (isAuthError(error)) {
          clearSession()
          return
        }
        setStatus('restore_failed')
      })

    return () => controller.abort()
  }, [clearSession, restoreKey, status, token])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      token,
      user,
      login: async (email, password) => {
        const session = await apiRequest<AuthSession>('/auth/login', {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        })
        storeSession(session)
      },
      register: async (email, password) => {
        const session = await apiRequest<AuthSession>('/auth/register', {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        })
        storeSession(session)
      },
      logout: clearSession,
      retryRestore: () => {
        if (token) {
          setStatus('restoring')
          setRestoreKey((value) => value + 1)
        }
      },
      handleAuthError: (error) => {
        if (isAuthError(error)) {
          clearSession()
          return true
        }
        return error instanceof ApiError && error.code.startsWith('AUTH_')
      },
    }),
    [clearSession, status, storeSession, token, user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthSessionProvider')
  }
  return context
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const location = useLocation()
  const { status } = useAuth()

  if (status === 'restoring') {
    return <div className="app-loading">Restoring session...</div>
  }
  if (status === 'restore_failed') {
    return <RestoreFailed />
  }
  if (status !== 'authenticated') {
    return <Navigate replace state={{ reason: 'expired', from: location }} to="/auth" />
  }
  return children
}

function RestoreFailed() {
  const { retryRestore } = useAuth()

  return (
    <div className="app-loading">
      <div className="restore-error">
        <p>Session restore failed.</p>
        <button className="ghost-button" type="button" onClick={retryRestore}>
          Retry
        </button>
      </div>
    </div>
  )
}

export function RedirectAuthenticated({ children }: { children: ReactNode }) {
  const { status } = useAuth()

  if (status === 'restoring') {
    return <div className="app-loading">Restoring session...</div>
  }
  if (status === 'authenticated') {
    return <Navigate replace to="/terminal" />
  }
  return children
}

function readStoredToken() {
  const sessionToken = sessionStorage.getItem(tokenStorageKey)
  if (sessionToken) {
    localStorage.removeItem(tokenStorageKey)
    return sessionToken
  }
  const legacyToken = localStorage.getItem(tokenStorageKey)
  if (legacyToken) {
    localStorage.removeItem(tokenStorageKey)
    sessionStorage.setItem(tokenStorageKey, legacyToken)
  }
  return legacyToken
}
