import { apiRequest } from '@/shared/api'

export type WatchlistItem = {
  ticker: string
  position: number
  created_at: string
}

export async function fetchWatchlist(token: string, signal?: AbortSignal) {
  const response = await apiRequest<{ items: WatchlistItem[] }>('/watchlist', {}, { token, signal })
  return response.items
}
