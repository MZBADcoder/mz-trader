import { apiRequest } from '@/shared/api'

export type BarItem = {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  vw: number | null
  trade_count: number
  is_final: boolean
  is_synthetic: boolean
}

export type BarsMeta = {
  ticker: string
  resolution: string
  session: string
  adjustment: string
  fill: string
  requested_from: string | null
  requested_to: string | null
  effective_from: string | null
  effective_to: string | null
  effective_trading_day: string | null
  market_timezone: string
  source_granularity: string
  data_source: string
  partial_range: boolean
  readiness: 'degraded' | 'failed' | 'initializing' | 'pending' | 'ready'
  calendar_shifted: boolean
  contains_partial_bar: boolean
  delay_minutes: number
  request_id: string
}

export type BarsResponse = {
  bars: BarItem[]
  meta: BarsMeta
}

export type SupportedBarAdjustment = 'split_adjusted'

export type BarsQuery = {
  ticker: string
  resolution: string
  session: string
  adjustment: SupportedBarAdjustment
  count_back?: number
  lookback_days?: number
}

export async function fetchBars(token: string, query: BarsQuery, signal?: AbortSignal) {
  const requestQuery: Record<string, boolean | number | string> = {
    ticker: query.ticker,
    resolution: query.resolution,
    session: query.session,
    adjustment: query.adjustment,
    fill: 'carry_forward',
    include_partial: true,
  }

  if (query.lookback_days !== undefined) {
    const to = new Date()
    const from = new Date(to.getTime() - query.lookback_days * 24 * 60 * 60 * 1000)
    requestQuery.from = from.toISOString()
    requestQuery.to = to.toISOString()
  } else if (query.count_back !== undefined) {
    requestQuery.count_back = query.count_back
  }

  return apiRequest<BarsResponse>(
    '/market-data/bars',
    {},
    {
      token,
      signal,
      query: requestQuery,
    },
  )
}
