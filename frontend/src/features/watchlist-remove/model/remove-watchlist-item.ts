import { apiRequest } from '@/shared/api'

export async function removeWatchlistItem(token: string, ticker: string) {
  await apiRequest<void>(
    `/watchlist/items/${encodeURIComponent(ticker)}`,
    { method: 'DELETE' },
    { token },
  )
}
