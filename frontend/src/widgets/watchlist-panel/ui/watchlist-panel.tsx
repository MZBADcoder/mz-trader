import { type FormEvent, useState } from 'react'

import { type SnapshotItem } from '@/entities/market-snapshot'
import { type WatchlistItem } from '@/entities/watchlist'
import { appConfig } from '@/shared/config'
import { useI18n } from '@/shared/i18n'
import { classNames, formatCompactNumber, formatCurrency, formatPercent } from '@/shared/lib'

type Props = {
  addError: string | null
  isAdding: boolean
  items: WatchlistItem[]
  rows: Map<string, SnapshotItem>
  selectedTicker: string | null
  staleTickers: Set<string>
  onAdd: (ticker: string) => Promise<boolean>
  onRemove: (ticker: string) => Promise<void>
  onSelect: (ticker: string) => void
}

export function WatchlistPanel({
  addError,
  isAdding,
  items,
  onAdd,
  onRemove,
  onSelect,
  rows,
  selectedTicker,
  staleTickers,
}: Props) {
  const { locale, t } = useI18n()
  const [ticker, setTicker] = useState('')
  const [removingTicker, setRemovingTicker] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!ticker.trim()) {
      return
    }
    const added = await onAdd(ticker)
    if (added) {
      setTicker('')
    }
  }

  async function handleRemove(nextTicker: string) {
    setRemovingTicker(nextTicker)
    try {
      await onRemove(nextTicker)
    } finally {
      setRemovingTicker(null)
    }
  }

  return (
    <aside className="watchlist-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">{t('terminal.limit')}</p>
          <h2>{t('terminal.watchlist')}</h2>
        </div>
        <span>
          {items.length}/{appConfig.maxWatchlistItems}
        </span>
      </div>

      <form className="ticker-form" onSubmit={handleSubmit}>
        <input
          aria-label={t('terminal.addTicker')}
          placeholder={t('terminal.tickerPlaceholder')}
          value={ticker}
          onChange={(event) => setTicker(event.target.value)}
        />
        <button
          className="primary-button"
          disabled={isAdding || items.length >= appConfig.maxWatchlistItems}
          type="submit"
        >
          {t('terminal.addTicker')}
        </button>
      </form>
      {addError ? <p className="inline-error">{addError}</p> : null}

      <div className="watchlist-rows">
        {items.map((item) => {
          const snapshot = rows.get(item.ticker)
          const stale = staleTickers.has(item.ticker)
          const direction = snapshot && snapshot.change >= 0 ? 'positive' : 'negative'
          const selected = selectedTicker === item.ticker
          return (
            <div
              className={classNames('watchlist-row', selected && 'selected', stale && 'stale')}
              key={item.ticker}
            >
              <button className="watchlist-row-main" type="button" onClick={() => onSelect(item.ticker)}>
                <span className="ticker-cell">
                  <strong>{item.ticker}</strong>
                  <small>{snapshot?.market_status ?? t('terminal.marketStatus')}</small>
                </span>
                <span className="price-cell">
                  <strong>{formatCurrency(snapshot?.last, locale)}</strong>
                  <small className={direction}>{formatPercent(snapshot?.change_pct, locale)}</small>
                </span>
                <span className="volume-cell">
                  <small>{t('terminal.volume')}</small>
                  <strong>{formatCompactNumber(snapshot?.volume, locale)}</strong>
                </span>
              </button>
              <button
                aria-label={`${t('terminal.remove')} ${item.ticker}`}
                className="remove-button"
                type="button"
                onClick={() => void handleRemove(item.ticker)}
              >
                {removingTicker === item.ticker ? '...' : 'x'}
              </button>
            </div>
          )
        })}
      </div>
    </aside>
  )
}
