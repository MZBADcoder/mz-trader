import { apiRequest } from '@/shared/api'

export type MarketDataCapabilities = {
  delay_minutes: number
  is_realtime: boolean
  supports_stream: boolean
}

export async function fetchMarketDataCapabilities(token: string, signal?: AbortSignal) {
  const response = await apiRequest<{ market_data: MarketDataCapabilities }>(
    '/market-data/capabilities',
    {},
    { token, signal },
  )
  return response.market_data
}
