import { apiRequest } from '@/shared/api'

export type SnapshotItem = {
  ticker: string
  last: number
  regular_close: number
  change: number
  change_pct: number
  open: number
  high: number
  low: number
  volume: number
  prev_close: number
  market_status: string
  session: string
  trading_day: string | null
  last_session: string | null
  last_trade_at: string | null
  delay_minutes: number
  is_realtime: boolean
  provider_updated_at: string
}

export type SnapshotsMeta = {
  delay_minutes: number
  is_realtime: boolean
  request_id: string
}

export type SnapshotsResponse = {
  items: SnapshotItem[]
  meta: SnapshotsMeta
}

export async function fetchSnapshots(token: string, tickers: string[], signal?: AbortSignal) {
  return apiRequest<SnapshotsResponse>(
    '/market-data/snapshots',
    {},
    {
      token,
      signal,
      query: { tickers: tickers.join(',') },
    },
  )
}
