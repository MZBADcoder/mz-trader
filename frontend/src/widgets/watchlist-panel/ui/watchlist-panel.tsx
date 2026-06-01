import { type DragEvent, type FormEvent, useState } from 'react'

import { type SnapshotItem } from '@/entities/market-snapshot'
import { type WatchlistItem } from '@/entities/watchlist'
import { appConfig } from '@/shared/config'
import { useI18n } from '@/shared/i18n'
import { classNames, formatCompactNumber, formatCurrency, formatPercent } from '@/shared/lib'

type Props = {
  addError: string | null
  isAdding: boolean
  isReordering: boolean
  items: WatchlistItem[]
  rows: Map<string, SnapshotItem>
  selectedTicker: string | null
  staleTickers: Set<string>
  onAdd: (ticker: string) => Promise<boolean>
  onRemove: (ticker: string) => Promise<void>
  onReorder: (tickers: string[]) => Promise<boolean>
  onSelect: (ticker: string) => void
}

export function WatchlistPanel({
  addError,
  isAdding,
  isReordering,
  items,
  onAdd,
  onRemove,
  onReorder,
  onSelect,
  rows,
  selectedTicker,
  staleTickers,
}: Props) {
  const { locale, t } = useI18n()
  const [ticker, setTicker] = useState('')
  const [removingTicker, setRemovingTicker] = useState<string | null>(null)
  const [draggedTicker, setDraggedTicker] = useState<string | null>(null)
  const [dropTargetTicker, setDropTargetTicker] = useState<string | null>(null)
  const [isEditingOrder, setEditingOrder] = useState(false)
  const [draftTickers, setDraftTickers] = useState<string[]>([])
  const visibleItems = isEditingOrder ? orderItemsByTickers(items, draftTickers) : items
  const orderChanged = isEditingOrder && !hasSameTickerOrder(items, draftTickers)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!ticker.trim() || isEditingOrder || isReordering) {
      return
    }
    const added = await onAdd(ticker)
    if (added) {
      setTicker('')
    }
  }

  async function handleRemove(nextTicker: string) {
    if (isEditingOrder || isReordering) {
      return
    }
    setRemovingTicker(nextTicker)
    try {
      await onRemove(nextTicker)
    } finally {
      setRemovingTicker(null)
    }
  }

  function handleDragStart(event: DragEvent<HTMLButtonElement>, nextTicker: string) {
    if (!isEditingOrder || isReordering) {
      event.preventDefault()
      return
    }
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', nextTicker)
    setDraggedTicker(nextTicker)
    setDropTargetTicker(null)
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>, nextTicker: string) {
    if (!isEditingOrder || isReordering || !draggedTicker || draggedTicker === nextTicker) {
      return
    }
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
    setDropTargetTicker(nextTicker)
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>, nextTicker: string) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setDropTargetTicker((current) => (current === nextTicker ? null : current))
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>, targetTicker: string) {
    event.preventDefault()
    if (!isEditingOrder || isReordering) {
      resetDragState()
      return
    }

    const sourceTicker = event.dataTransfer.getData('text/plain') || draggedTicker
    resetDragState()
    if (!sourceTicker || sourceTicker === targetTicker) {
      return
    }

    setDraftTickers((current) => moveTickerToTargetSlot(current, sourceTicker, targetTicker))
  }

  function resetDragState() {
    setDraggedTicker(null)
    setDropTargetTicker(null)
  }

  function startEditingOrder() {
    setDraftTickers(items.map((item) => item.ticker))
    setEditingOrder(true)
    resetDragState()
  }

  function cancelEditingOrder() {
    setEditingOrder(false)
    setDraftTickers([])
    resetDragState()
  }

  async function saveOrder() {
    const saved = await onReorder(draftTickers)
    if (saved) {
      setEditingOrder(false)
      setDraftTickers([])
      resetDragState()
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

      <div className="watchlist-order-actions">
        {isEditingOrder ? (
          <>
            <button
              className="ghost-button compact-button"
              disabled={isReordering}
              type="button"
              onClick={cancelEditingOrder}
            >
              {t('terminal.cancelOrder')}
            </button>
            <button
              className="primary-button compact-button"
              disabled={isReordering || !orderChanged}
              type="button"
              onClick={() => void saveOrder()}
            >
              {isReordering ? t('terminal.savingOrder') : t('terminal.saveOrder')}
            </button>
          </>
        ) : (
          <button
            className="ghost-button compact-button"
            disabled={items.length < 2 || isAdding || isReordering}
            type="button"
            onClick={startEditingOrder}
          >
            {t('terminal.editOrder')}
          </button>
        )}
      </div>

      <form className="ticker-form" onSubmit={handleSubmit}>
        <input
          aria-label={t('terminal.addTicker')}
          disabled={isEditingOrder || isReordering}
          placeholder={t('terminal.tickerPlaceholder')}
          value={ticker}
          onChange={(event) => setTicker(event.target.value)}
        />
        <button
          className="primary-button"
          disabled={isAdding || isEditingOrder || isReordering || items.length >= appConfig.maxWatchlistItems}
          type="submit"
        >
          {t('terminal.addTicker')}
        </button>
      </form>
      {addError ? <p className="inline-error">{addError}</p> : null}
      {isEditingOrder ? <p className="order-hint">{t('terminal.orderHint')}</p> : null}

      <div className="watchlist-rows">
        {visibleItems.map((item) => {
          const snapshot = rows.get(item.ticker)
          const stale = staleTickers.has(item.ticker)
          const direction = snapshot && snapshot.change >= 0 ? 'positive' : 'negative'
          const selected = selectedTicker === item.ticker
          return (
            <div
              className={classNames(
                'watchlist-row',
                selected && 'selected',
                stale && 'stale',
                draggedTicker === item.ticker && 'dragging',
                dropTargetTicker === item.ticker && 'drop-target',
              )}
              key={item.ticker}
              onDragLeave={(event) => handleDragLeave(event, item.ticker)}
              onDragOver={(event) => handleDragOver(event, item.ticker)}
              onDrop={(event) => handleDrop(event, item.ticker)}
            >
              <button
                aria-label={`${t('terminal.reorder')} ${item.ticker}`}
                className="drag-handle"
                disabled={!isEditingOrder || isReordering}
                draggable={isEditingOrder && !isReordering && items.length > 1}
                type="button"
                onDragEnd={resetDragState}
                onDragStart={(event) => handleDragStart(event, item.ticker)}
              >
                ::
              </button>
              <button
                className="watchlist-row-main"
                disabled={isEditingOrder || isReordering}
                type="button"
                onClick={() => onSelect(item.ticker)}
              >
                <span className="ticker-cell">
                  <strong>{item.ticker}</strong>
                  <small>
                    {snapshot?.session ? snapshotSessionLabel(snapshot.session, t) : t('terminal.marketStatus')}
                  </small>
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
                disabled={isEditingOrder || isReordering}
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

function moveTickerToTargetSlot(tickers: string[], sourceTicker: string, targetTicker: string) {
  const sourceIndex = tickers.indexOf(sourceTicker)
  const targetIndex = tickers.indexOf(targetTicker)
  if (sourceIndex === -1 || targetIndex === -1) {
    return tickers
  }

  const nextTickers = [...tickers]
  const [source] = nextTickers.splice(sourceIndex, 1)
  nextTickers.splice(targetIndex, 0, source)
  return nextTickers
}

function orderItemsByTickers(items: WatchlistItem[], tickers: string[]) {
  const itemByTicker = new Map(items.map((item) => [item.ticker, item]))
  return tickers
    .map((ticker) => itemByTicker.get(ticker))
    .filter((item): item is WatchlistItem => item !== undefined)
}

function snapshotSessionLabel(session: string, t: (key: `terminal.${string}`) => string) {
  if (session === 'pre_market') {
    return t('terminal.marketPreMarket')
  }
  if (session === 'regular') {
    return t('terminal.marketOpen')
  }
  if (session === 'after_hours') {
    return t('terminal.marketAfterHours')
  }
  if (session === 'closed') {
    return t('terminal.marketClosed')
  }
  return t('terminal.marketStatus')
}

function hasSameTickerOrder(items: WatchlistItem[], tickers: string[]) {
  return items.length === tickers.length && items.every((item, index) => item.ticker === tickers[index])
}
