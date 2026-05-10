import { useMemo, useState } from 'react'

import { type BarItem, type BarsMeta } from '@/entities/market-bars'
import { useBarsPolling, type BarsRefreshState } from '@/features/bars-refresh'
import { BarsQueryControls, type BarsControlsValue } from '@/features/bars-query-controls'
import { ApiError } from '@/shared/api'
import { useI18n } from '@/shared/i18n'
import { classNames, formatCompactNumber, formatCurrency, formatDateTime } from '@/shared/lib'

type Props = {
  selectedTicker: string | null
  token: string
  onAuthExpired: () => void
}

const defaultControls: BarsControlsValue = {
  adjustment: 'split_adjusted',
  resolution: '5m',
  session: 'regular',
}

export function ChartWorkspace({ onAuthExpired, selectedTicker, token }: Props) {
  const { locale, t } = useI18n()
  const [controls, setControls] = useState<BarsControlsValue>(defaultControls)
  const barsQuery = useMemo(
    () =>
      selectedTicker
        ? {
            ticker: selectedTicker,
            resolution: controls.resolution,
            session: controls.session,
            adjustment: controls.adjustment,
            count_back: 180,
          }
        : null,
    [controls.adjustment, controls.resolution, controls.session, selectedTicker],
  )
  const barsPolling = useBarsPolling(token, barsQuery, onAuthExpired)
  const { bars, error, isLoading, meta, state } = barsPolling

  const chartState = useMemo(() => getChartState(meta, state, isLoading, error, bars.length, t), [
    bars.length,
    error,
    isLoading,
    meta,
    state,
    t,
  ])

  if (!selectedTicker) {
    return (
      <section className="chart-workspace empty">
        <h2>{t('terminal.emptyWatchlistTitle')}</h2>
        <p>{t('terminal.emptyWatchlistText')}</p>
      </section>
    )
  }

  return (
    <section className="chart-workspace">
      <header className="chart-header">
        <div>
          <p className="eyebrow">{t('terminal.chart')}</p>
          <h1>{selectedTicker}</h1>
          <p>
            {meta?.effective_from
              ? formatDateTime(meta.effective_from, locale, { timeZone: meta.market_timezone })
              : '-'} /
            {meta?.source_granularity ?? '-'} / {meta?.data_source ?? '-'}
          </p>
        </div>
        <div className={classNames('readiness-pill', chartState.kind)}>
          {chartState.label}
        </div>
      </header>

      <BarsQueryControls
        error={error ? mapBarsQueryValidationError(error, t) : null}
        value={controls}
        onChange={setControls}
      />

      <div className="chart-surface">
        {isLoading ? <div className="chart-overlay">{t('common.loading')}</div> : null}
        {!isLoading && chartState.kind === 'failed' ? (
          <div className="chart-overlay">{chartState.label}</div>
        ) : null}
        {!isLoading && chartState.kind !== 'failed' && bars.length === 0 ? (
          <div className="chart-overlay">{t('terminal.noBars')}</div>
        ) : null}
        {bars.length ? <BarsSvg bars={bars} locale={locale} /> : null}
      </div>

      <footer className="chart-footer">
        <span>{meta?.partial_range ? t('terminal.partialRange') : t('terminal.readinessReady')}</span>
        <span>{meta?.contains_partial_bar ? t('terminal.containsPartial') : t('terminal.readinessReady')}</span>
        <span>{formatCompactNumber(bars.at(-1)?.volume, locale)} vol</span>
      </footer>
    </section>
  )
}

function BarsSvg({ bars, locale }: { bars: BarItem[]; locale: string }) {
  const width = 960
  const priceHeight = 360
  const volumeHeight = 100
  const padding = 28
  const closes = bars.map((bar) => bar.close)
  const volumes = bars.map((bar) => bar.volume)
  const minPrice = Math.min(...closes)
  const maxPrice = Math.max(...closes)
  const maxVolume = Math.max(...volumes, 1)
  const priceSpan = Math.max(maxPrice - minPrice, 0.01)
  const step = bars.length > 1 ? (width - padding * 2) / (bars.length - 1) : 0

  const points = bars
    .map((bar, index) => {
      const x = padding + index * step
      const y = padding + ((maxPrice - bar.close) / priceSpan) * (priceHeight - padding * 2)
      return `${x},${y}`
    })
    .join(' ')

  const latest = bars.at(-1)

  return (
    <svg className="bars-svg" role="img" viewBox={`0 0 ${width} ${priceHeight + volumeHeight}`}>
      <title>{latest ? `${latest.time} ${latest.close}` : 'Bars chart'}</title>
      <g className="grid-lines">
        {[0, 1, 2, 3].map((line) => {
          const y = padding + line * ((priceHeight - padding * 2) / 3)
          return <line key={line} x1={padding} x2={width - padding} y1={y} y2={y} />
        })}
      </g>
      <polyline className="price-line" fill="none" points={points} />
      <g className="volume-bars">
        {bars.map((bar, index) => {
          const x = padding + index * step
          const height = (bar.volume / maxVolume) * (volumeHeight - 18)
          return (
            <rect
              height={height}
              key={`${bar.time}-${index}`}
              width={Math.max(2, step * 0.6)}
              x={x}
              y={priceHeight + volumeHeight - height - 8}
            />
          )
        })}
      </g>
      <text x={padding} y={priceHeight + volumeHeight - 8}>
        {latest ? `${formatCurrency(latest.close, locale)} close` : ''}
      </text>
    </svg>
  )
}

function getChartState(
  meta: BarsMeta | null,
  state: BarsRefreshState,
  isLoading: boolean,
  error: ApiError | null,
  count: number,
  t: (key: `common.${string}` | `terminal.${string}`) => string,
) {
  if (isLoading) {
    return { kind: 'loading', label: t('common.loading') }
  }
  if (state === 'degraded') {
    return count
      ? { kind: 'degraded', label: t('terminal.readinessDegraded') }
      : { kind: 'failed', label: t('terminal.barsError') }
  }
  if (error) {
    return { kind: 'failed', label: t('terminal.barsError') }
  }
  if (!meta) {
    return { kind: 'pending', label: t('terminal.readinessPending') }
  }
  if (meta.readiness === 'failed') {
    return { kind: 'failed', label: t('terminal.readinessFailed') }
  }
  if (meta.readiness === 'pending') {
    return { kind: 'pending', label: t('terminal.readinessPending') }
  }
  if (meta.readiness === 'initializing') {
    return { kind: 'initializing', label: t('terminal.readinessInitializing') }
  }
  if (meta.readiness === 'degraded') {
    return { kind: 'degraded', label: t('terminal.readinessDegraded') }
  }
  if (!count) {
    return { kind: 'pending', label: t('terminal.noBars') }
  }
  return { kind: 'ready', label: t('terminal.readinessReady') }
}

function mapBarsQueryValidationError(error: ApiError, t: (key: `terminal.${string}`) => string) {
  if (error.code === 'MARKET_BARS_UNSUPPORTED_SESSION_RESOLUTION') {
    return t('terminal.unsupportedCombination')
  }
  if (
    error.code === 'MARKET_BARS_RANGE_INVALID' ||
    error.code === 'MARKET_BARS_RANGE_TOO_LARGE' ||
    error.code === 'MARKET_BARS_QUERY_MODE_INVALID'
  ) {
    return t('terminal.barsRangeInvalid')
  }
  if (
    error.code === 'MARKET_BARS_RESOLUTION_UNSUPPORTED' ||
    error.code === 'MARKET_BARS_SESSION_UNSUPPORTED' ||
    error.code === 'MARKET_BARS_ADJUSTMENT_UNSUPPORTED'
  ) {
    return t('terminal.barsUnsupported')
  }
  if (
    error.code === 'MARKET_BARS_COUNT_BACK_INVALID' ||
    error.code === 'MARKET_BARS_COUNT_BACK_TOO_LARGE'
  ) {
    return t('terminal.barsCountInvalid')
  }
  return null
}
