import { AuthPanel, RedirectAuthenticated } from '@/features/auth'

export function AuthPage() {
  return (
    <RedirectAuthenticated>
      <AuthPanel />
    </RedirectAuthenticated>
  )
}
