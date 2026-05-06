import { createContext, createElement, type ReactNode, useContext, useMemo, useState } from 'react'

import enAuth from './locales/en-US/auth.json'
import enCommon from './locales/en-US/common.json'
import enHome from './locales/en-US/home.json'
import enTerminal from './locales/en-US/terminal.json'
import zhAuth from './locales/zh-CN/auth.json'
import zhCommon from './locales/zh-CN/common.json'
import zhHome from './locales/zh-CN/home.json'
import zhTerminal from './locales/zh-CN/terminal.json'

export type Locale = 'en-US' | 'zh-CN'
type Namespace = 'auth' | 'common' | 'home' | 'terminal'
type Dictionary = Record<Namespace, Record<string, string>>

const localeStorageKey = 'trade-helper.locale'

const dictionaries: Record<Locale, Dictionary> = {
  'en-US': {
    auth: enAuth,
    common: enCommon,
    home: enHome,
    terminal: enTerminal,
  },
  'zh-CN': {
    auth: zhAuth,
    common: zhCommon,
    home: zhHome,
    terminal: zhTerminal,
  },
}

type I18nContextValue = {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: (key: `${Namespace}.${string}`) => string
}

const I18nContext = createContext<I18nContextValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale)

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale: (nextLocale) => {
        localStorage.setItem(localeStorageKey, nextLocale)
        setLocaleState(nextLocale)
      },
      t: (key) => {
        const [namespace, messageKey] = key.split('.') as [Namespace, string]
        return dictionaries[locale][namespace]?.[messageKey] ?? key
      },
    }),
    [locale],
  )

  return createElement(I18nContext.Provider, { value }, children)
}

export function useI18n() {
  const context = useContext(I18nContext)
  if (!context) {
    throw new Error('useI18n must be used within I18nProvider')
  }
  return context
}

function readStoredLocale(): Locale {
  const stored = localStorage.getItem(localeStorageKey)
  if (stored === 'en-US' || stored === 'zh-CN') {
    return stored
  }
  return navigator.language.startsWith('zh') ? 'zh-CN' : 'en-US'
}
