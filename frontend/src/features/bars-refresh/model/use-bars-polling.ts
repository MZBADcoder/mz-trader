import { useEffect, useMemo, useState } from 'react'

import { fetchBars, type BarItem, type BarsMeta, type BarsQuery } from '@/entities/market-bars'
import { ApiError, isAuthError } from '@/shared/api'
import { appConfig } from '@/shared/config'

export type BarsRefreshState = 'degraded' | 'fresh' | 'idle' | 'loading'

export type BarsPollingResult = {
  bars: BarItem[]
  error: ApiError | null
  isLoading: boolean
  meta: BarsMeta | null
  refreshNow: () => void
  state: BarsRefreshState
}

export function useBarsPolling(
  token: string,
  query: BarsQuery | null,
  onAuthExpired: () => void,
): BarsPollingResult {
  const [data, setData] = useState<{ bars: BarItem[]; key: string; meta: BarsMeta } | null>(null)
  const [pollState, setPollState] = useState<{
    error: ApiError | null
    key: string
    state: BarsRefreshState
  }>({ error: null, key: '', state: 'idle' })
  const [manualRefreshKey, setManualRefreshKey] = useState(0)
  const queryKey = query
    ? [
        query.ticker,
        query.resolution,
        query.session,
        query.adjustment,
        query.count_back ?? '',
        query.lookback_days ?? '',
      ].join('|')
    : ''

  useEffect(() => {
    if (!query) {
      return
    }

    const activeQuery = query
    const activeQueryKey = queryKey
    let timeoutId: number | undefined
    let isFirstPoll = true
    const controller = new AbortController()

    async function poll() {
      if (isFirstPoll) {
        setPollState({ error: null, key: activeQueryKey, state: 'loading' })
      }

      try {
        const response = await fetchBars(token, activeQuery, controller.signal)
        setData({ bars: response.bars, key: activeQueryKey, meta: response.meta })
        setPollState({ error: null, key: activeQueryKey, state: 'fresh' })
        isFirstPoll = false
        timeoutId = window.setTimeout(poll, appConfig.barsPollMs)
      } catch (unknownError) {
        if (controller.signal.aborted) {
          return
        }
        if (isAuthError(unknownError)) {
          onAuthExpired()
          return
        }
        setPollState({
          error: unknownError instanceof ApiError ? unknownError : null,
          key: activeQueryKey,
          state: 'degraded',
        })
        isFirstPoll = false
        if (!isTerminalBarsQueryError(unknownError)) {
          timeoutId = window.setTimeout(poll, appConfig.barsRetryMs)
        }
      }
    }

    poll()

    return () => {
      controller.abort()
      window.clearTimeout(timeoutId)
    }
  }, [manualRefreshKey, onAuthExpired, query, queryKey, token])

  const hasCurrentData = data?.key === queryKey
  const currentState = query ? (pollState.key === queryKey ? pollState.state : 'loading') : 'idle'

  return useMemo(
    () => ({
      bars: hasCurrentData ? data.bars : [],
      error: pollState.key === queryKey ? pollState.error : null,
      isLoading: currentState === 'loading',
      meta: hasCurrentData ? data.meta : null,
      refreshNow: () => setManualRefreshKey((value) => value + 1),
      state: currentState,
    }),
    [currentState, data, hasCurrentData, pollState.error, pollState.key, queryKey],
  )
}

const terminalBarsQueryErrorCodes = new Set([
  'MARKET_BARS_ADJUSTMENT_UNSUPPORTED',
  'MARKET_BARS_COUNT_BACK_INVALID',
  'MARKET_BARS_COUNT_BACK_TOO_LARGE',
  'MARKET_BARS_QUERY_MODE_INVALID',
  'MARKET_BARS_RANGE_INVALID',
  'MARKET_BARS_RANGE_TOO_LARGE',
  'MARKET_BARS_RESOLUTION_UNSUPPORTED',
  'MARKET_BARS_SESSION_UNSUPPORTED',
  'MARKET_BARS_UNSUPPORTED_SESSION_RESOLUTION',
])

function isTerminalBarsQueryError(error: unknown) {
  return error instanceof ApiError && terminalBarsQueryErrorCodes.has(error.code)
}
