import { type WatchlistItem } from '@/entities/watchlist'
import { apiRequest } from '@/shared/api'

export async function addWatchlistItem(token: string, ticker: string) {
  const response = await apiRequest<{ item: WatchlistItem }>(
    '/watchlist/items',
    {
      method: 'POST',
      body: JSON.stringify({ ticker: ticker.trim() }),
    },
    { token },
  )
  return response.item
}
