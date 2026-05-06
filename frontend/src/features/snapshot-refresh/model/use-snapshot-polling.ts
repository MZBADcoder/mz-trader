import { useEffect, useMemo, useState } from 'react'

import { fetchSnapshots, type SnapshotItem, type SnapshotsMeta } from '@/entities/market-snapshot'
import { ApiError, isAuthError } from '@/shared/api'
import { appConfig } from '@/shared/config'

export type SnapshotRefreshState = 'degraded' | 'fresh' | 'idle' | 'loading' | 'partial'

export type SnapshotPollingResult = {
  error: ApiError | null
  lastUpdatedAt: string | null
  meta: SnapshotsMeta | null
  rows: Map<string, SnapshotItem>
  staleTickers: Set<string>
  state: SnapshotRefreshState
  refreshNow: () => void
}

export function useSnapshotPolling(
  token: string,
  tickers: string[],
  onAuthExpired: () => void,
): SnapshotPollingResult {
  const [rows, setRows] = useState<Map<string, SnapshotItem>>(new Map())
  const [staleTickers, setStaleTickers] = useState<Set<string>>(new Set())
  const [state, setState] = useState<SnapshotRefreshState>('idle')
  const [meta, setMeta] = useState<SnapshotsMeta | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [manualRefreshKey, setManualRefreshKey] = useState(0)
  const key = tickers.join(',')

  useEffect(() => {
    if (!tickers.length) {
      return
    }

    let timeoutId: number | undefined
    const controller = new AbortController()

    async function poll() {
      setState((previous) => (previous === 'idle' ? 'loading' : previous))
      try {
        const response = await fetchSnapshots(token, tickers, controller.signal)
        const responseByTicker = new Map(response.items.map((item) => [item.ticker, item]))
        const returnedTickers = new Set(responseByTicker.keys())
        setRows((previousRows) => {
          const nextRows = new Map<string, SnapshotItem>()
          tickers.forEach((ticker) => {
            const item = responseByTicker.get(ticker) ?? previousRows.get(ticker)
            if (item) {
              nextRows.set(ticker, item)
            }
          })
          return nextRows
        })
        const missing = tickers.filter((ticker) => !returnedTickers.has(ticker))
        setStaleTickers(new Set(missing))
        setMeta(response.meta)
        setError(null)
        setState(missing.length ? 'partial' : 'fresh')
        timeoutId = window.setTimeout(poll, appConfig.snapshotPollMs)
      } catch (unknownError) {
        if (controller.signal.aborted) {
          return
        }
        if (isAuthError(unknownError)) {
          onAuthExpired()
          return
        }
        setError(unknownError instanceof ApiError ? unknownError : null)
        setState('degraded')
        timeoutId = window.setTimeout(poll, appConfig.snapshotRetryMs)
      }
    }

    poll()

    return () => {
      controller.abort()
      window.clearTimeout(timeoutId)
    }
  }, [key, manualRefreshKey, onAuthExpired, tickers, token])

  const activeRows = useMemo(() => {
    if (!tickers.length) {
      return new Map<string, SnapshotItem>()
    }
    const nextRows = new Map<string, SnapshotItem>()
    tickers.forEach((ticker) => {
      const row = rows.get(ticker)
      if (row) {
        nextRows.set(ticker, row)
      }
    })
    return nextRows
  }, [rows, tickers])

  const activeStaleTickers = useMemo(() => {
    if (!tickers.length) {
      return new Set<string>()
    }
    const activeTickers = new Set(tickers)
    return new Set([...staleTickers].filter((ticker) => activeTickers.has(ticker)))
  }, [staleTickers, tickers])

  return useMemo(
    () => ({
      error,
      lastUpdatedAt: tickers.length ? newestProviderUpdatedAt(activeRows) : null,
      meta: tickers.length ? meta : null,
      refreshNow: () => setManualRefreshKey((value) => value + 1),
      rows: activeRows,
      staleTickers: activeStaleTickers,
      state: tickers.length ? state : 'idle',
    }),
    [activeRows, activeStaleTickers, error, meta, state, tickers.length],
  )
}

function newestProviderUpdatedAt(rows: Map<string, SnapshotItem>) {
  let newest: string | null = null
  rows.forEach((row) => {
    if (!newest || row.provider_updated_at > newest) {
      newest = row.provider_updated_at
    }
  })
  return newest
}
