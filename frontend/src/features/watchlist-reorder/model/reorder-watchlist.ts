import { apiRequest } from '@/shared/api'
import { type WatchlistItem } from '@/entities/watchlist'

type ReorderWatchlistResponse = {
  items: WatchlistItem[]
}

export async function reorderWatchlist(token: string, tickers: string[], signal?: AbortSignal) {
  const response = await apiRequest<ReorderWatchlistResponse>(
    '/watchlist',
    {
      method: 'PATCH',
      body: JSON.stringify({ tickers }),
    },
    { token, signal },
  )
  return response.items
}
