import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { fetchMarketDataCapabilities, type MarketDataCapabilities } from '@/entities/market-capabilities'
import { fetchWatchlist, type WatchlistItem } from '@/entities/watchlist'
import { useAuth } from '@/features/auth'
import { addWatchlistItem } from '@/features/watchlist-add'
import { removeWatchlistItem } from '@/features/watchlist-remove'
import { reorderWatchlist } from '@/features/watchlist-reorder'
import { firstTicker, nextTickerAfterRemoval } from '@/features/ticker-selection'
import { useSnapshotPolling } from '@/features/snapshot-refresh'
import { ApiError, isAuthError } from '@/shared/api'
import { useI18n } from '@/shared/i18n'

import { ChartWorkspace } from '@/widgets/chart-workspace'
import { MarketStatusBar } from '@/widgets/market-status-bar'
import { WatchlistPanel } from '@/widgets/watchlist-panel'

export function TerminalShell() {
  const { logout, token, user } = useAuth()
  const { locale, setLocale, t } = useI18n()
  const navigate = useNavigate()
  const [items, setItems] = useState<WatchlistItem[]>([])
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null)
  const [capabilities, setCapabilities] = useState<MarketDataCapabilities | null>(null)
  const [isLoading, setLoading] = useState(true)
  const [isAdding, setAdding] = useState(false)
  const [isReordering, setReordering] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)
  const [terminalError, setTerminalError] = useState<string | null>(null)
  const reorderInFlightRef = useRef(false)

  const handleAuthExpired = useCallback(() => {
    logout()
    navigate('/auth', { replace: true, state: { reason: 'expired' } })
  }, [logout, navigate])

  useEffect(() => {
    if (!token) {
      return
    }

    const controller = new AbortController()
    Promise.all([
      fetchWatchlist(token, controller.signal),
      fetchMarketDataCapabilities(token, controller.signal),
    ])
      .then(([watchlistItems, nextCapabilities]) => {
        setItems(watchlistItems)
        setCapabilities(nextCapabilities)
        setSelectedTicker((current) => current ?? firstTicker(watchlistItems))
        setTerminalError(null)
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return
        }
        if (isAuthError(error)) {
          handleAuthExpired()
          return
        }
        setTerminalError(mapTerminalError(error, t))
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      })

    return () => controller.abort()
  }, [handleAuthExpired, t, token])

  const tickers = useMemo(() => items.map((item) => item.ticker), [items])
  const snapshotPolling = useSnapshotPolling(token ?? '', tickers, handleAuthExpired)

  async function handleAddTicker(ticker: string) {
    if (!token || reorderInFlightRef.current) {
      return false
    }
    setAdding(true)
    setAddError(null)
    try {
      const item = await addWatchlistItem(token, ticker)
      setItems((previous) => {
        const next = [...previous, item]
        setSelectedTicker((current) => current ?? item.ticker)
        return next
      })
      return true
    } catch (error) {
      if (isAuthError(error)) {
        handleAuthExpired()
        return false
      }
      setAddError(mapWatchlistError(error, t))
      return false
    } finally {
      setAdding(false)
    }
  }

  async function handleRemoveTicker(ticker: string) {
    if (!token || reorderInFlightRef.current) {
      return
    }
    try {
      await removeWatchlistItem(token, ticker)
      setItems((previous) => {
        const next = previous.filter((item) => item.ticker !== ticker)
        setSelectedTicker((current) => nextTickerAfterRemoval(previous, ticker, current))
        return next
      })
    } catch (error) {
      if (isAuthError(error)) {
        handleAuthExpired()
        return
      }
      setTerminalError(mapTerminalError(error, t))
    }
  }

  async function handleReorderTickers(tickers: string[]) {
    if (!token || reorderInFlightRef.current) {
      return false
    }

    const previousItems = items
    const nextItems = orderItemsByTickers(previousItems, tickers)
    if (hasSameOrder(previousItems, nextItems)) {
      return true
    }

    reorderInFlightRef.current = true
    setReordering(true)
    setItems(nextItems)
    setTerminalError(null)
    try {
      const updatedItems = await reorderWatchlist(token, tickers)
      setItems(updatedItems)
      setSelectedTicker((current) => current ?? firstTicker(updatedItems))
      return true
    } catch (error) {
      setItems(previousItems)
      if (isAuthError(error)) {
        handleAuthExpired()
        return false
      }
      setTerminalError(mapTerminalError(error, t))
      return false
    } finally {
      reorderInFlightRef.current = false
      setReordering(false)
    }
  }

  if (!token) {
    return null
  }

  return (
    <main className="terminal-page">
      <header className="terminal-topbar">
        <div>
          <Link className="brand-link" to="/">
            {t('common.brand')}
          </Link>
          <span>{user?.email}</span>
        </div>
        <div className="topbar-actions">
          <label className="locale-control">
            <span>{t('common.language')}</span>
            <select value={locale} onChange={(event) => setLocale(event.target.value as typeof locale)}>
              <option value="zh-CN">{t('common.zh')}</option>
              <option value="en-US">{t('common.en')}</option>
            </select>
          </label>
          <button className="ghost-button" type="button" onClick={logout}>
            {t('common.logout')}
          </button>
        </div>
      </header>

      {terminalError ? <p className="notice error">{terminalError}</p> : null}
      <MarketStatusBar
        capabilities={capabilities}
        lastUpdatedAt={snapshotPolling.lastUpdatedAt}
        state={snapshotPolling.state}
        onRefresh={snapshotPolling.refreshNow}
      />

      <div className="terminal-layout">
        <WatchlistPanel
          addError={addError}
          isAdding={isAdding}
          isReordering={isReordering}
          items={items}
          rows={snapshotPolling.rows}
          selectedTicker={selectedTicker}
          staleTickers={snapshotPolling.staleTickers}
          onAdd={handleAddTicker}
          onRemove={handleRemoveTicker}
          onReorder={handleReorderTickers}
          onSelect={setSelectedTicker}
        />
        <ChartWorkspace
          selectedTicker={isLoading ? null : selectedTicker}
          token={token}
          onAuthExpired={handleAuthExpired}
        />
      </div>
    </main>
  )
}

function orderItemsByTickers(items: WatchlistItem[], tickers: string[]) {
  const itemByTicker = new Map(items.map((item) => [item.ticker, item]))
  return tickers
    .map((ticker, position) => {
      const item = itemByTicker.get(ticker)
      return item ? { ...item, position } : null
    })
    .filter((item): item is WatchlistItem => item !== null)
}

function hasSameOrder(currentItems: WatchlistItem[], nextItems: WatchlistItem[]) {
  return (
    currentItems.length === nextItems.length &&
    currentItems.every((item, index) => item.ticker === nextItems[index]?.ticker)
  )
}

function mapWatchlistError(error: unknown, t: (key: `auth.${string}` | `terminal.${string}`) => string) {
  if (error instanceof ApiError) {
    if (error.code === 'WATCHLIST_TICKER_DUPLICATE') {
      return t('terminal.duplicate')
    }
    if (error.code === 'WATCHLIST_LIMIT_EXCEEDED') {
      return t('terminal.limitExceeded')
    }
    if (error.code === 'WATCHLIST_TICKER_INVALID') {
      return t('terminal.tickerInvalid')
    }
    if (error.code === 'WATCHLIST_TICKER_NOT_SUPPORTED') {
      return t('terminal.tickerUnsupported')
    }
    return t('auth.backendError')
  }
  return t('auth.backendError')
}

function mapTerminalError(
  error: unknown,
  t: (key: `common.${string}` | `terminal.${string}`) => string,
) {
  if (error instanceof ApiError) {
    if (error.code === 'WATCHLIST_TICKER_NOT_FOUND') {
      return t('terminal.tickerNotFound')
    }
    if (error.code === 'MARKET_SNAPSHOT_UPSTREAM_UNAVAILABLE') {
      return t('terminal.snapshotsDegraded')
    }
    if (error.code === 'WATCHLIST_ORDER_INVALID') {
      return t('terminal.reorderInvalid')
    }
  }
  return t('common.error')
}
