import { appConfig } from '@/shared/config'

export type ApiErrorBody = {
  code: string
  message: string
  detail: string
  request_id: string
}

type ApiErrorEnvelope = {
  error?: ApiErrorBody
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly detail: string
  readonly requestId: string

  constructor(status: number, body?: ApiErrorBody) {
    const code = body?.code ?? (status === 401 ? 'AUTH_REQUIRED' : 'API_ERROR')
    super(getSafeApiErrorMessage(status, code))
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.detail = body?.detail ?? ''
    this.requestId = body?.request_id ?? ''
  }
}

export type RequestOptions = {
  token?: string | null
  signal?: AbortSignal
  query?: Record<string, boolean | number | string | null | undefined>
}

export async function apiRequest<TResponse>(
  path: string,
  init: RequestInit = {},
  options: RequestOptions = {},
): Promise<TResponse> {
  const url = new URL(`${appConfig.apiBaseUrl}${path}`)
  Object.entries(options.query ?? {}).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') {
      url.searchParams.set(key, String(value))
    }
  })

  const headers = new Headers(init.headers)
  if (!headers.has('Content-Type') && init.body !== undefined) {
    headers.set('Content-Type', 'application/json')
  }
  if (options.token) {
    headers.set('Authorization', `Bearer ${options.token}`)
  }

  const response = await fetch(url, {
    ...init,
    headers,
    signal: options.signal,
  })

  if (response.status === 204) {
    return undefined as TResponse
  }

  const text = await response.text()
  const data = parseJson(text)

  if (!response.ok) {
    throw new ApiError(response.status, normalizeErrorBody(data, response.status))
  }

  return data as TResponse
}

function parseJson(text: string): unknown {
  if (!text) {
    return undefined
  }
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

function normalizeErrorBody(data: unknown, status: number): ApiErrorBody {
  const envelope = data as ApiErrorEnvelope | undefined
  if (envelope?.error) {
    return envelope.error
  }
  return {
    code: status === 401 ? 'AUTH_REQUIRED' : 'API_ERROR',
    message: status === 401 ? 'Authentication is required.' : 'Request failed.',
    detail: '',
    request_id: '',
  }
}

export function isAuthError(error: unknown) {
  return error instanceof ApiError && error.status === 401
}

function getSafeApiErrorMessage(status: number, code: string) {
  if (code === 'AUTH_REQUIRED' || code === 'AUTH_TOKEN_INVALID' || code === 'AUTH_TOKEN_EXPIRED') {
    return 'Authentication is required.'
  }
  if (code === 'AUTH_INVALID_CREDENTIALS') {
    return 'Email or password is incorrect.'
  }
  if (code === 'AUTH_EMAIL_ALREADY_EXISTS') {
    return 'Email is already registered.'
  }
  if (code === 'WATCHLIST_TICKER_DUPLICATE') {
    return 'Ticker already exists in the watchlist.'
  }
  if (code === 'WATCHLIST_LIMIT_EXCEEDED') {
    return 'Watchlist limit reached.'
  }
  if (status === 401) {
    return 'Authentication is required.'
  }
  return 'Request failed.'
}
