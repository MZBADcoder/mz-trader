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
            count_back: 260,
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

      <IndicatorLegend bars={bars} locale={locale} title={t('terminal.indicators')} />

      <footer className="chart-footer">
        <span>{meta?.partial_range ? t('terminal.partialRange') : t('terminal.readinessReady')}</span>
        <span>{meta?.contains_partial_bar ? t('terminal.containsPartial') : t('terminal.readinessReady')}</span>
        <span>{formatCompactNumber(bars.at(-1)?.volume, locale)} vol</span>
      </footer>
    </section>
  )
}

function IndicatorLegend({ bars, locale, title }: { bars: BarItem[]; locale: string; title: string }) {
  const indicators = calculateIndicators(bars)
  const latest = indicators.at(-1)

  return (
    <div className="indicator-tools" aria-label={title}>
      <span className="indicator-title">{title}</span>
      <span className="indicator-pill">
        <span className="swatch violet" />
        BOLL {formatCurrency(latest?.bollMiddle, locale)}
      </span>
      <span className="indicator-pill">
        <span className="swatch blue" />
        MA 30 {formatCurrency(latest?.ma30, locale)}
      </span>
      <span className="indicator-pill">
        <span className="swatch amber" />
        MA 60 {formatCurrency(latest?.ma60, locale)}
      </span>
      <span className="indicator-pill">
        <span className="swatch white" />
        MA 200 {formatCurrency(latest?.ma200, locale)}
      </span>
    </div>
  )
}

function BarsSvg({ bars, locale }: { bars: BarItem[]; locale: string }) {
  const width = 960
  const priceHeight = 360
  const volumeHeight = 100
  const padding = 28
  const indicators = calculateIndicators(bars)
  const closes = bars.map((bar) => bar.close)
  const volumes = bars.map((bar) => bar.volume)
  const indicatorValues = indicators.flatMap((indicator) => [
    indicator.ma30,
    indicator.ma60,
    indicator.ma200,
    indicator.bollUpper,
    indicator.bollMiddle,
    indicator.bollLower,
  ])
  const priceValues = [
    ...bars.flatMap((bar) => [bar.high, bar.low, bar.close]),
    ...indicatorValues.filter((value): value is number => value !== null),
  ]
  const minPrice = Math.min(...priceValues)
  const maxPrice = Math.max(...priceValues)
  const maxVolume = Math.max(...volumes, 1)
  const priceSpan = Math.max(maxPrice - minPrice, 0.01)
  const step = bars.length > 1 ? (width - padding * 2) / (bars.length - 1) : 0

  const xForIndex = (index: number) => padding + index * step
  const yForPrice = (price: number) =>
    padding + ((maxPrice - price) / priceSpan) * (priceHeight - padding * 2)
  const closePath = buildLinePath(closes, xForIndex, yForPrice)
  const ma30Path = buildLinePath(
    indicators.map((indicator) => indicator.ma30),
    xForIndex,
    yForPrice,
  )
  const ma60Path = buildLinePath(
    indicators.map((indicator) => indicator.ma60),
    xForIndex,
    yForPrice,
  )
  const ma200Path = buildLinePath(
    indicators.map((indicator) => indicator.ma200),
    xForIndex,
    yForPrice,
  )
  const bollUpperPath = buildLinePath(
    indicators.map((indicator) => indicator.bollUpper),
    xForIndex,
    yForPrice,
  )
  const bollMiddlePath = buildLinePath(
    indicators.map((indicator) => indicator.bollMiddle),
    xForIndex,
    yForPrice,
  )
  const bollLowerPath = buildLinePath(
    indicators.map((indicator) => indicator.bollLower),
    xForIndex,
    yForPrice,
  )
  const bollBandPath = buildBandPath(
    indicators.map((indicator) => indicator.bollUpper),
    indicators.map((indicator) => indicator.bollLower),
    xForIndex,
    yForPrice,
  )

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
      {bollBandPath ? <path className="boll-band" d={bollBandPath} /> : null}
      <path className="indicator-line boll" d={bollUpperPath} />
      <path className="indicator-line boll middle" d={bollMiddlePath} />
      <path className="indicator-line boll" d={bollLowerPath} />
      <path className="indicator-line ma200" d={ma200Path} />
      <path className="indicator-line ma60" d={ma60Path} />
      <path className="indicator-line ma30" d={ma30Path} />
      <path className="price-line" d={closePath} fill="none" />
      <line className="volume-separator" x1={padding} x2={width - padding} y1={priceHeight} y2={priceHeight} />
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
      <text className="volume-axis-label" x={padding} y={priceHeight + 18}>
        VOL
      </text>
    </svg>
  )
}

type IndicatorPoint = {
  bollLower: number | null
  bollMiddle: number | null
  bollUpper: number | null
  ma30: number | null
  ma60: number | null
  ma200: number | null
}

function calculateIndicators(bars: BarItem[]): IndicatorPoint[] {
  const closes = bars.map((bar) => bar.close)
  return closes.map((_, index) => {
    const bollWindow = closes.slice(Math.max(0, index - 19), index + 1)
    const bollMiddle = bollWindow.length === 20 ? average(bollWindow) : null
    const deviation = bollMiddle === null ? null : standardDeviation(bollWindow, bollMiddle)
    return {
      bollLower: bollMiddle !== null && deviation !== null ? bollMiddle - deviation * 2 : null,
      bollMiddle,
      bollUpper: bollMiddle !== null && deviation !== null ? bollMiddle + deviation * 2 : null,
      ma30: simpleMovingAverage(closes, index, 30),
      ma60: simpleMovingAverage(closes, index, 60),
      ma200: simpleMovingAverage(closes, index, 200),
    }
  })
}

function simpleMovingAverage(values: number[], index: number, period: number) {
  if (index + 1 < period) {
    return null
  }
  return average(values.slice(index - period + 1, index + 1))
}

function average(values: number[]) {
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function standardDeviation(values: number[], mean: number) {
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length
  return Math.sqrt(variance)
}

function buildLinePath(
  values: Array<number | null>,
  xForIndex: (index: number) => number,
  yForPrice: (price: number) => number,
) {
  let d = ''
  values.forEach((value, index) => {
    if (value === null) {
      return
    }
    d += `${d ? ' L' : 'M'} ${xForIndex(index)},${yForPrice(value)}`
  })
  return d
}

function buildBandPath(
  upperValues: Array<number | null>,
  lowerValues: Array<number | null>,
  xForIndex: (index: number) => number,
  yForPrice: (price: number) => number,
) {
  const upperPoints = upperValues
    .map((value, index) => (value === null ? null : { x: xForIndex(index), y: yForPrice(value) }))
    .filter((point): point is { x: number; y: number } => point !== null)
  const lowerPoints = lowerValues
    .map((value, index) => (value === null ? null : { x: xForIndex(index), y: yForPrice(value) }))
    .filter((point): point is { x: number; y: number } => point !== null)

  if (!upperPoints.length || upperPoints.length !== lowerPoints.length) {
    return ''
  }

  const upperPath = upperPoints.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x},${point.y}`)
  const lowerPath = lowerPoints
    .slice()
    .reverse()
    .map((point) => `L ${point.x},${point.y}`)
  return [...upperPath, ...lowerPath, 'Z'].join(' ')
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
