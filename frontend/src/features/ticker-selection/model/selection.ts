import { type WatchlistItem } from '@/entities/watchlist'

export function nextTickerAfterRemoval(
  items: WatchlistItem[],
  removedTicker: string,
  currentTicker: string | null,
) {
  const remaining = items.filter((item) => item.ticker !== removedTicker)
  if (currentTicker !== removedTicker) {
    return currentTicker
  }
  return remaining[0]?.ticker ?? null
}

export function firstTicker(items: WatchlistItem[]) {
  return items[0]?.ticker ?? null
}
