import { RequireAuth } from '@/features/auth'
import { TerminalShell } from '@/widgets/terminal-shell'

export function TerminalPage() {
  return (
    <RequireAuth>
      <TerminalShell />
    </RequireAuth>
  )
}
