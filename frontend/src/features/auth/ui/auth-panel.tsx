import { type FormEvent, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '@/shared/api'
import { useI18n } from '@/shared/i18n'

import { useAuth } from '../model/auth-session'

type AuthMode = 'login' | 'register'

type LocationState = {
  reason?: string
}

export function AuthPanel() {
  const { t } = useI18n()
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const state = location.state as LocationState | null
  const [mode, setMode] = useState<AuthMode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)
  const [isSubmitting, setSubmitting] = useState(false)

  const submitLabel = mode === 'login' ? t('auth.submitLogin') : t('auth.submitRegister')
  const sessionMessage = state?.reason === 'expired' ? t('auth.expired') : null

  const formTitle = useMemo(
    () => (mode === 'login' ? t('auth.loginTab') : t('auth.registerTab')),
    [mode, t],
  )

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFieldError(null)
    setApiError(null)

    const validationError = validateForm(email, password, mode, t)
    if (validationError) {
      setFieldError(validationError)
      return
    }

    setSubmitting(true)
    try {
      if (mode === 'login') {
        await login(email.trim(), password)
      } else {
        await register(email.trim(), password)
      }
      navigate('/terminal', { replace: true })
    } catch (error) {
      setApiError(mapAuthError(error, t))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <Link className="brand-link" to="/">
        {t('common.brand')}
      </Link>
      <section className="auth-panel" aria-labelledby="auth-title">
        <div className="auth-copy">
          <p className="eyebrow">{formTitle}</p>
          <h1 id="auth-title">{t('auth.title')}</h1>
          <p>{t('auth.subtitle')}</p>
        </div>

        <div className="segmented" role="tablist" aria-label="Auth mode">
          <button
            aria-selected={mode === 'login'}
            className={mode === 'login' ? 'active' : ''}
            role="tab"
            type="button"
            onClick={() => setMode('login')}
          >
            {t('auth.loginTab')}
          </button>
          <button
            aria-selected={mode === 'register'}
            className={mode === 'register' ? 'active' : ''}
            role="tab"
            type="button"
            onClick={() => setMode('register')}
          >
            {t('auth.registerTab')}
          </button>
        </div>

        {sessionMessage ? <p className="notice warning">{sessionMessage}</p> : null}
        {fieldError ? <p className="notice error">{fieldError}</p> : null}
        {apiError ? <p className="notice error">{apiError}</p> : null}

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            <span>{t('auth.email')}</span>
            <input
              autoComplete="email"
              inputMode="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label>
            <span>{t('auth.password')}</span>
            <input
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <button className="primary-button" disabled={isSubmitting} type="submit">
            {isSubmitting ? t('common.loading') : submitLabel}
          </button>
        </form>
      </section>
    </main>
  )
}

function validateForm(
  email: string,
  password: string,
  mode: AuthMode,
  t: (key: 'auth.emailInvalid' | 'auth.emailRequired' | 'auth.passwordRequired' | 'auth.passwordTooShort') => string,
) {
  if (!email.trim()) {
    return t('auth.emailRequired')
  }
  if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
    return t('auth.emailInvalid')
  }
  if (!password) {
    return t('auth.passwordRequired')
  }
  if (mode === 'register' && password.length < 8) {
    return t('auth.passwordTooShort')
  }
  return null
}

function mapAuthError(error: unknown, t: (key: `auth.${string}`) => string) {
  if (error instanceof ApiError) {
    if (error.code === 'AUTH_INVALID_CREDENTIALS') {
      return t('auth.invalidCredentials')
    }
    if (error.code === 'AUTH_EMAIL_ALREADY_EXISTS') {
      return t('auth.emailExists')
    }
  }
  return t('auth.backendError')
}
