import { apiRequest } from '@/shared/api'

export type User = {
  id: string
  email: string
}

export type AuthSession = {
  user: User
  access_token: string
  token_type: string
  expires_in: number
}

export async function fetchCurrentUser(token: string, signal?: AbortSignal) {
  const response = await apiRequest<{ user: User }>('/auth/me', {}, { token, signal })
  return response.user
}
