import type { PropsWithChildren } from 'react'

import { AuthSessionProvider } from '@/features/auth'
import { I18nProvider } from '@/shared/i18n'

export function AppProvider({ children }: PropsWithChildren) {
  return (
    <I18nProvider>
      <AuthSessionProvider>{children}</AuthSessionProvider>
    </I18nProvider>
  )
}
