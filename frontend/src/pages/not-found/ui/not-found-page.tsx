import { Navigate } from 'react-router-dom'

import { useAuth } from '@/features/auth'

export function NotFoundPage() {
  const { status } = useAuth()
  if (status === 'restoring') {
    return <div className="app-loading">Restoring session...</div>
  }
  return <Navigate replace to={status === 'authenticated' ? '/terminal' : '/auth'} />
}
