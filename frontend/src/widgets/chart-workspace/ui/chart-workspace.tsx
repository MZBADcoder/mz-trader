import { type PointerEvent, useMemo, useRef, useState } from 'react'

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
  resolution: 'intraday',
  session: 'regular',
}
const intradayHistoryLookbackDays = 14
const higherTimeframeCountBack = 260

export function ChartWorkspace({ onAuthExpired, selectedTicker, token }: Props) {
  const { locale, t } = useI18n()
  const [controls, setControls] = useState<BarsControlsValue>(defaultControls)
  const isTimeShareMode = controls.resolution === 'intraday'
  const showIndicators = !isTimeShareMode && !isIntradayResolution(controls.resolution)
  const barsQuery = useMemo(
    () =>
      selectedTicker
        ? {
            ticker: selectedTicker,
            resolution: isTimeShareMode ? '1m' : controls.resolution,
            session: controls.session,
            adjustment: controls.adjustment,
            ...(isTimeShareMode
              ? {}
              : isIntradayResolution(controls.resolution)
              ? { lookback_days: intradayHistoryLookbackDays }
              : { count_back: higherTimeframeCountBack }),
          }
        : null,
    [controls.adjustment, controls.resolution, controls.session, isTimeShareMode, selectedTicker],
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
        {bars.length && isTimeShareMode ? (
          <TimeShareSvg bars={bars} locale={locale} marketTimezone={meta?.market_timezone ?? 'UTC'} />
        ) : null}
        {bars.length && !isTimeShareMode ? (
          <BarsSvg
            bars={bars}
            locale={locale}
            marketTimezone={meta?.market_timezone ?? 'UTC'}
            showIndicators={showIndicators}
          />
        ) : null}
      </div>

      {showIndicators ? <IndicatorLegend bars={bars} locale={locale} title={t('terminal.indicators')} /> : null}

      <footer className="chart-footer">
        <span>{meta?.partial_range ? t('terminal.partialRange') : t('terminal.readinessReady')}</span>
        <span>{meta?.contains_partial_bar ? t('terminal.containsPartial') : t('terminal.readinessReady')}</span>
        <span>{formatCompactNumber(bars.at(-1)?.volume, locale)} vol</span>
      </footer>
    </section>
  )
}

function isIntradayResolution(resolution: string) {
  return resolution.endsWith('m')
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

function TimeShareSvg({
  bars,
  locale,
  marketTimezone,
}: {
  bars: BarItem[]
  locale: string
  marketTimezone: string
}) {
  const width = 960
  const priceHeight = 360
  const volumeHeight = 100
  const timeAxisHeight = 34
  const totalHeight = priceHeight + volumeHeight + timeAxisHeight
  const padding = 28
  const priceAxisWidth = 72
  const plotLeft = padding
  const plotRight = width - padding - priceAxisWidth
  const sessionMinuteSlots = 390
  const visibleBars = bars.slice(0, sessionMinuteSlots)
  const volumes = visibleBars.map((bar) => bar.volume)
  const priceValues = visibleBars.flatMap((bar) => [bar.open, bar.high, bar.low, bar.close])
  const minPrice = Math.min(...priceValues)
  const maxPrice = Math.max(...priceValues)
  const maxVolume = Math.max(...volumes, 1)
  const priceSpan = Math.max(maxPrice - minPrice, 0.01)
  const step = visibleBars.length ? (plotRight - plotLeft) / sessionMinuteSlots : 0
  const volumeWidth = Math.max(1.4, Math.min(3, step * 0.72))
  const xForIndex = (index: number) => plotLeft + step / 2 + index * step
  const yForPrice = (price: number) =>
    padding + ((maxPrice - price) / priceSpan) * (priceHeight - padding * 2)
  const linePath = buildLinePath(
    visibleBars.map((bar) => bar.close),
    xForIndex,
    yForPrice,
  )
  const areaPath = buildAreaPath(
    visibleBars.map((bar) => bar.close),
    xForIndex,
    yForPrice,
    priceHeight,
  )
  const timeTicks = buildTimeShareTicks(visibleBars, xForIndex)
  const priceTicks = buildPriceTicks(minPrice, maxPrice, 4).map((price) => ({
    price,
    y: yForPrice(price),
  }))
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const latest = visibleBars.at(-1)
  const earliest = visibleBars[0]
  const hoveredBar = hoverIndex === null ? null : visibleBars[hoverIndex]
  const hoveredX = hoverIndex === null ? null : xForIndex(hoverIndex)
  const hoveredCloseY = hoveredBar ? yForPrice(hoveredBar.close) : null

  const handlePointerHover = (event: PointerEvent<SVGSVGElement>) => {
    if (!step) {
      return
    }
    const rect = event.currentTarget.getBoundingClientRect()
    const svgX = ((event.clientX - rect.left) / rect.width) * width
    const svgY = ((event.clientY - rect.top) / rect.height) * totalHeight
    const isInPlotArea = svgX >= plotLeft && svgX <= plotRight && svgY >= padding && svgY <= priceHeight + volumeHeight
    if (!isInPlotArea) {
      setHoverIndex(null)
      return
    }
    const nextHoverIndex = Math.round((svgX - plotLeft - step / 2) / step)
    setHoverIndex(nextHoverIndex >= 0 && nextHoverIndex < visibleBars.length ? nextHoverIndex : null)
  }

  return (
    <svg
      aria-label="Intraday time-sharing chart"
      className="bars-svg"
      onPointerLeave={() => setHoverIndex(null)}
      onPointerMove={handlePointerHover}
      role="img"
      viewBox={`0 0 ${width} ${totalHeight}`}
    >
      <title>
        {latest
          ? `${earliest?.time ?? ''} - ${latest.time} close ${latest.close} volume ${latest.volume}`
          : 'Intraday time-sharing chart'}
      </title>
      <g className="grid-lines">
        {priceTicks.map((tick) => (
          <line key={tick.price} x1={plotLeft} x2={plotRight} y1={tick.y} y2={tick.y} />
        ))}
      </g>
      <g className="price-axis">
        <line x1={plotRight} x2={plotRight} y1={padding} y2={priceHeight - padding} />
        {priceTicks.map((tick) => (
          <text dominantBaseline="middle" key={tick.price} x={plotRight + 10} y={tick.y}>
            {formatAxisPrice(tick.price, locale)}
          </text>
        ))}
      </g>
      {areaPath ? <path className="timeshare-area" d={areaPath} /> : null}
      {linePath ? <path className="timeshare-line" d={linePath} /> : null}
      <line className="volume-separator" x1={plotLeft} x2={plotRight} y1={priceHeight} y2={priceHeight} />
      <g className="volume-bars">
        {visibleBars.map((bar, index) => {
          const x = xForIndex(index)
          const height = (bar.volume / maxVolume) * (volumeHeight - 18)
          const direction = bar.close > bar.open ? 'up' : bar.close < bar.open ? 'down' : 'flat'
          return (
            <rect
              className={direction}
              height={height}
              key={`${bar.time}-${index}`}
              width={volumeWidth}
              x={x - volumeWidth / 2}
              y={priceHeight + volumeHeight - height - 8}
            />
          )
        })}
      </g>
      <text className="volume-axis-label" x={plotLeft} y={priceHeight + 18}>
        VOL
      </text>
      <g className="time-axis">
        <line x1={plotLeft} x2={plotRight} y1={priceHeight + volumeHeight + 1} y2={priceHeight + volumeHeight + 1} />
        {timeTicks.map((tick) => (
          <g key={`${tick.index}-${tick.time}`}>
            <line x1={tick.x} x2={tick.x} y1={priceHeight + volumeHeight + 1} y2={priceHeight + volumeHeight + 7} />
            <text textAnchor={tick.anchor} x={tick.x} y={priceHeight + volumeHeight + 24}>
              {formatAxisTime(tick.time, locale, marketTimezone, visibleBars)}
            </text>
          </g>
        ))}
      </g>
      {hoveredBar && hoveredX !== null && hoveredCloseY !== null ? (
        <TimeShareHoverDetails
          bar={hoveredBar}
          closeY={hoveredCloseY}
          locale={locale}
          marketTimezone={marketTimezone}
          maxX={plotRight}
          priceHeight={priceHeight}
          x={hoveredX}
        />
      ) : null}
    </svg>
  )
}

function TimeShareHoverDetails({
  bar,
  closeY,
  locale,
  marketTimezone,
  maxX,
  priceHeight,
  x,
}: {
  bar: BarItem
  closeY: number
  locale: string
  marketTimezone: string
  maxX: number
  priceHeight: number
  x: number
}) {
  const tooltipWidth = 172
  const tooltipHeight = 82
  const tooltipX = x > maxX - tooltipWidth - 28 ? x - tooltipWidth - 14 : x + 14
  const tooltipY = closeY > tooltipHeight + 18 ? closeY - tooltipHeight - 12 : closeY + 16

  return (
    <g className="hover-layer">
      <line className="crosshair-line" x1={x} x2={x} y1={28} y2={priceHeight + 100} />
      <line className="crosshair-line" x1={28} x2={maxX} y1={closeY} y2={closeY} />
      <circle className="crosshair-dot" cx={x} cy={closeY} r={4} />
      <g className="ohlc-tooltip" transform={`translate(${tooltipX} ${tooltipY})`}>
        <rect height={tooltipHeight} rx={6} width={tooltipWidth} />
        <text className="tooltip-time" x={10} y={20}>
          {formatDateTime(bar.time, locale, { timeZone: marketTimezone })}
        </text>
        <text x={10} y={45}>
          Price {formatCurrency(bar.close, locale)}
        </text>
        <text x={10} y={66}>
          V {formatCompactNumber(bar.volume, locale)}
        </text>
      </g>
    </g>
  )
}

function BarsSvg({
  bars,
  locale,
  marketTimezone,
  showIndicators,
}: {
  bars: BarItem[]
  locale: string
  marketTimezone: string
  showIndicators: boolean
}) {
  const width = 960
  const priceHeight = 360
  const volumeHeight = 100
  const timeAxisHeight = 34
  const totalHeight = priceHeight + volumeHeight + timeAxisHeight
  const padding = 28
  const priceAxisWidth = 72
  const plotLeft = padding
  const plotRight = width - padding - priceAxisWidth
  const visibleLimit = 92
  const visibleSlotCount = visibleLimit
  const indicators = showIndicators ? calculateIndicators(bars) : []
  const visibleCount = Math.min(bars.length, visibleLimit)
  const maxWindowStart = Math.max(0, bars.length - visibleCount)
  const barsKey = `${bars[0]?.time ?? ''}:${bars.at(-1)?.time ?? ''}:${bars.length}`
  const [windowState, setWindowState] = useState(() => ({
    barsKey,
    windowStart: maxWindowStart,
  }))
  const [isDragging, setIsDragging] = useState(false)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const dragRef = useRef<{
    pointerId: number
    startWindow: number
    startX: number
    step: number
  } | null>(null)
  const windowStart =
    windowState.barsKey === barsKey ? clamp(windowState.windowStart, 0, maxWindowStart) : maxWindowStart

  const visibleBars = bars.slice(windowStart, windowStart + visibleCount)
  const visibleIndicators = showIndicators ? indicators.slice(windowStart, windowStart + visibleCount) : []
  const volumes = visibleBars.map((bar) => bar.volume)
  const indicatorValues = showIndicators
    ? visibleIndicators.flatMap((indicator) => [
        indicator.ma30,
        indicator.ma60,
        indicator.ma200,
        indicator.bollUpper,
        indicator.bollMiddle,
        indicator.bollLower,
      ])
    : []
  const priceValues = [
    ...visibleBars.flatMap((bar) => [bar.open, bar.high, bar.low, bar.close]),
    ...indicatorValues.filter((value): value is number => value !== null),
  ]
  const minPrice = Math.min(...priceValues)
  const maxPrice = Math.max(...priceValues)
  const maxVolume = Math.max(...volumes, 1)
  const priceSpan = Math.max(maxPrice - minPrice, 0.01)
  const step = visibleBars.length ? (plotRight - plotLeft) / visibleSlotCount : 0
  const candleWidth = Math.max(4, Math.min(12, step * 0.58))
  const volumeWidth = Math.max(2, Math.min(candleWidth, step * 0.7))

  const xForIndex = (index: number) => plotLeft + step / 2 + index * step
  const yForPrice = (price: number) =>
    padding + ((maxPrice - price) / priceSpan) * (priceHeight - padding * 2)
  const ma30Path = buildLinePath(
    visibleIndicators.map((indicator) => indicator.ma30),
    xForIndex,
    yForPrice,
  )
  const ma60Path = buildLinePath(
    visibleIndicators.map((indicator) => indicator.ma60),
    xForIndex,
    yForPrice,
  )
  const ma200Path = buildLinePath(
    visibleIndicators.map((indicator) => indicator.ma200),
    xForIndex,
    yForPrice,
  )
  const bollUpperPath = buildLinePath(
    visibleIndicators.map((indicator) => indicator.bollUpper),
    xForIndex,
    yForPrice,
  )
  const bollMiddlePath = buildLinePath(
    visibleIndicators.map((indicator) => indicator.bollMiddle),
    xForIndex,
    yForPrice,
  )
  const bollLowerPath = buildLinePath(
    visibleIndicators.map((indicator) => indicator.bollLower),
    xForIndex,
    yForPrice,
  )
  const bollBandPath = buildBandPath(
    visibleIndicators.map((indicator) => indicator.bollUpper),
    visibleIndicators.map((indicator) => indicator.bollLower),
    xForIndex,
    yForPrice,
  )

  const latest = visibleBars.at(-1)
  const earliest = visibleBars[0]
  const canPan = maxWindowStart > 0
  const hoveredBar = hoverIndex === null ? null : visibleBars[hoverIndex]
  const hoveredX = hoverIndex === null ? null : xForIndex(hoverIndex)
  const hoveredCloseY = hoveredBar ? yForPrice(hoveredBar.close) : null
  const timeTicks = buildTimeTicks(visibleBars, xForIndex)
  const priceTicks = buildPriceTicks(minPrice, maxPrice, 4).map((price) => ({
    price,
    y: yForPrice(price),
  }))

  const handlePointerDown = (event: PointerEvent<SVGSVGElement>) => {
    if (!canPan || !step) {
      return
    }
    dragRef.current = {
      pointerId: event.pointerId,
      startWindow: windowStart,
      startX: event.clientX,
      step,
    }
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    setHoverIndex(null)
    setIsDragging(true)
  }

  const handlePointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) {
      return
    }
    event.preventDefault()
    const deltaBars = Math.round((drag.startX - event.clientX) / drag.step)
    setWindowState({
      barsKey,
      windowStart: clamp(drag.startWindow + deltaBars, 0, maxWindowStart),
    })
    setHoverIndex(null)
  }

  const handlePointerHover = (event: PointerEvent<SVGSVGElement>) => {
    if (dragRef.current || !step) {
      return
    }
    const rect = event.currentTarget.getBoundingClientRect()
    const svgX = ((event.clientX - rect.left) / rect.width) * width
    const svgY = ((event.clientY - rect.top) / rect.height) * totalHeight
    const isInPlotArea = svgX >= plotLeft && svgX <= plotRight && svgY >= padding && svgY <= priceHeight + volumeHeight
    if (!isInPlotArea) {
      setHoverIndex(null)
      return
    }
    const nextHoverIndex = Math.round((svgX - plotLeft - step / 2) / step)
    setHoverIndex(nextHoverIndex >= 0 && nextHoverIndex < visibleBars.length ? nextHoverIndex : null)
  }

  const handlePointerEnd = (event: PointerEvent<SVGSVGElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) {
      dragRef.current = null
      setIsDragging(false)
    }
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }

  const handlePointerLeave = () => {
    if (!dragRef.current) {
      setHoverIndex(null)
    }
  }

  return (
    <svg
      aria-label="Candlestick chart"
      className={classNames('bars-svg', canPan && 'pannable', isDragging && 'dragging')}
      onPointerCancel={handlePointerEnd}
      onPointerDown={handlePointerDown}
      onPointerLeave={handlePointerLeave}
      onPointerMove={(event) => {
        handlePointerMove(event)
        handlePointerHover(event)
      }}
      onPointerUp={handlePointerEnd}
      role="img"
      viewBox={`0 0 ${width} ${totalHeight}`}
    >
      <title>
        {latest
          ? `${earliest?.time ?? ''} - ${latest.time} open ${latest.open} high ${latest.high} low ${latest.low} close ${latest.close} volume ${latest.volume}`
          : 'Candlestick chart'}
      </title>
      <g className="grid-lines">
        {priceTicks.map((tick) => (
          <line key={tick.price} x1={plotLeft} x2={plotRight} y1={tick.y} y2={tick.y} />
        ))}
      </g>
      <g className="price-axis">
        <line x1={plotRight} x2={plotRight} y1={padding} y2={priceHeight - padding} />
        {priceTicks.map((tick) => (
          <text dominantBaseline="middle" key={tick.price} x={plotRight + 10} y={tick.y}>
            {formatAxisPrice(tick.price, locale)}
          </text>
        ))}
      </g>
      {showIndicators && bollBandPath ? <path className="boll-band" d={bollBandPath} /> : null}
      <g className="candles">
        {visibleBars.map((bar, index) => {
          const x = xForIndex(index)
          const openY = yForPrice(bar.open)
          const closeY = yForPrice(bar.close)
          const bodyY = Math.min(openY, closeY)
          const bodyHeight = Math.max(1, Math.abs(closeY - openY))
          const direction = bar.close > bar.open ? 'up' : bar.close < bar.open ? 'down' : 'flat'
          return (
            <g
              className={classNames(
                'candle',
                direction,
                !bar.is_final && 'partial',
                bar.is_synthetic && 'synthetic',
              )}
              key={`${bar.time}-${index}`}
            >
              <line className="wick" x1={x} x2={x} y1={yForPrice(bar.high)} y2={yForPrice(bar.low)} />
              <rect
                className="body"
                height={bodyHeight}
                rx={1}
                width={candleWidth}
                x={x - candleWidth / 2}
                y={bodyY}
              />
            </g>
          )
        })}
      </g>
      {showIndicators ? (
        <>
          <path className="indicator-line boll" d={bollUpperPath} />
          <path className="indicator-line boll middle" d={bollMiddlePath} />
          <path className="indicator-line boll" d={bollLowerPath} />
          <path className="indicator-line ma200" d={ma200Path} />
          <path className="indicator-line ma60" d={ma60Path} />
          <path className="indicator-line ma30" d={ma30Path} />
        </>
      ) : null}
      <line className="volume-separator" x1={plotLeft} x2={plotRight} y1={priceHeight} y2={priceHeight} />
      <g className="volume-bars">
        {visibleBars.map((bar, index) => {
          const x = xForIndex(index)
          const height = (bar.volume / maxVolume) * (volumeHeight - 18)
          const direction = bar.close > bar.open ? 'up' : bar.close < bar.open ? 'down' : 'flat'
          return (
            <rect
              className={direction}
              height={height}
              key={`${bar.time}-${index}`}
              width={volumeWidth}
              x={x - volumeWidth / 2}
              y={priceHeight + volumeHeight - height - 8}
            />
          )
        })}
      </g>
      <text className="volume-axis-label" x={plotLeft} y={priceHeight + 18}>
        VOL
      </text>
      <g className="time-axis">
        <line x1={plotLeft} x2={plotRight} y1={priceHeight + volumeHeight + 1} y2={priceHeight + volumeHeight + 1} />
        {timeTicks.map((tick) => (
          <g key={`${tick.index}-${tick.time}`}>
            <line x1={tick.x} x2={tick.x} y1={priceHeight + volumeHeight + 1} y2={priceHeight + volumeHeight + 7} />
            <text textAnchor={tick.anchor} x={tick.x} y={priceHeight + volumeHeight + 24}>
              {formatAxisTime(tick.time, locale, marketTimezone, visibleBars)}
            </text>
          </g>
        ))}
      </g>
      {hoveredBar && hoveredX !== null && hoveredCloseY !== null ? (
        <HoverDetails
          bar={hoveredBar}
          closeY={hoveredCloseY}
          locale={locale}
          marketTimezone={marketTimezone}
          maxX={plotRight}
          priceHeight={priceHeight}
          x={hoveredX}
        />
      ) : null}
    </svg>
  )
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

function buildTimeTicks(bars: BarItem[], xForIndex: (index: number) => number) {
  if (!bars.length) {
    return []
  }
  const minTickSpacing = 72
  const targetIndexes = [0, 0.25, 0.5, 0.75, 1].map((ratio) =>
    Math.round((bars.length - 1) * ratio),
  )
  const indexes = [...new Set(targetIndexes)]
    .filter((index) => bars[index])
    .reduce<number[]>((visibleIndexes, index) => {
      const previousIndex = visibleIndexes.at(-1)
      if (previousIndex !== undefined && xForIndex(index) - xForIndex(previousIndex) < minTickSpacing) {
        return visibleIndexes
      }
      return [...visibleIndexes, index]
    }, [])
  return indexes.map((index, position) => ({
    anchor: getTimeTickAnchor(position, indexes.length),
    index,
    time: bars[index].time,
    x: xForIndex(index),
  }))
}

function buildTimeShareTicks(bars: BarItem[], xForIndex: (index: number) => number) {
  if (!bars.length) {
    return []
  }
  const minTickSpacing = 120
  const targetRatios = bars.length < 120 ? [0, 1] : [0, 0.25, 0.5, 0.75, 1]
  const targetIndexes = targetRatios.map((ratio) => Math.round((bars.length - 1) * ratio))
  const indexes = [...new Set(targetIndexes)]
    .filter((index) => bars[index])
    .reduce<number[]>((visibleIndexes, index) => {
      const previousIndex = visibleIndexes.at(-1)
      if (previousIndex !== undefined && xForIndex(index) - xForIndex(previousIndex) < minTickSpacing) {
        return visibleIndexes
      }
      return [...visibleIndexes, index]
    }, [])

  return indexes.map((index, position) => ({
    anchor: getTimeTickAnchor(position, indexes.length),
    index,
    time: bars[index].time,
    x: xForIndex(index),
  }))
}

function getTimeTickAnchor(position: number, count: number): 'end' | 'middle' | 'start' {
  if (position === 0) {
    return 'start'
  }
  if (position === count - 1) {
    return 'end'
  }
  return 'middle'
}

function formatAxisTime(time: string, locale: string, marketTimezone: string, bars: BarItem[]) {
  const firstTime = bars[0]?.time
  const lastTime = bars.at(-1)?.time
  const durationMs = firstTime && lastTime ? new Date(lastTime).getTime() - new Date(firstTime).getTime() : 0
  const options: Intl.DateTimeFormatOptions =
    durationMs > 36 * 60 * 60 * 1000
      ? { day: '2-digit', month: 'short', timeZone: marketTimezone }
      : { hour: '2-digit', minute: '2-digit', timeZone: marketTimezone }
  return new Intl.DateTimeFormat(locale, options).format(new Date(time))
}

function buildPriceTicks(minPrice: number, maxPrice: number, count: number) {
  if (count <= 1) {
    return [maxPrice]
  }
  const span = Math.max(maxPrice - minPrice, 0.01)
  return Array.from({ length: count }, (_, index) => maxPrice - (span * index) / (count - 1))
}

function formatAxisPrice(price: number, locale: string) {
  const decimals = Math.abs(price) >= 1000 ? 0 : 2
  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  }).format(price)
}

function HoverDetails({
  bar,
  closeY,
  locale,
  marketTimezone,
  maxX,
  priceHeight,
  x,
}: {
  bar: BarItem
  closeY: number
  locale: string
  marketTimezone: string
  maxX: number
  priceHeight: number
  x: number
}) {
  const tooltipWidth = 184
  const tooltipHeight = 106
  const tooltipX = x > maxX - tooltipWidth - 28 ? x - tooltipWidth - 14 : x + 14
  const tooltipY = closeY > tooltipHeight + 18 ? closeY - tooltipHeight - 12 : closeY + 16
  return (
    <g className="hover-layer">
      <line className="crosshair-line" x1={x} x2={x} y1={28} y2={priceHeight + 100} />
      <line className="crosshair-line" x1={28} x2={maxX} y1={closeY} y2={closeY} />
      <circle className="crosshair-dot" cx={x} cy={closeY} r={4} />
      <g className="ohlc-tooltip" transform={`translate(${tooltipX} ${tooltipY})`}>
        <rect height={tooltipHeight} rx={6} width={tooltipWidth} />
        <text className="tooltip-time" x={10} y={20}>
          {formatDateTime(bar.time, locale, { timeZone: marketTimezone })}
        </text>
        <text x={10} y={42}>
          O {formatCurrency(bar.open, locale)}  H {formatCurrency(bar.high, locale)}
        </text>
        <text x={10} y={62}>
          L {formatCurrency(bar.low, locale)}  C {formatCurrency(bar.close, locale)}
        </text>
        <text x={10} y={84}>
          V {formatCompactNumber(bar.volume, locale)}
        </text>
      </g>
    </g>
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

function buildAreaPath(
  values: Array<number | null>,
  xForIndex: (index: number) => number,
  yForPrice: (price: number) => number,
  baselineY: number,
) {
  const points = values
    .map((value, index) => (value === null ? null : { x: xForIndex(index), y: yForPrice(value) }))
    .filter((point): point is { x: number; y: number } => point !== null)

  if (!points.length) {
    return ''
  }

  const line = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x},${point.y}`)
  const first = points[0]!
  const last = points[points.length - 1]!
  return [...line, `L ${last.x},${baselineY}`, `L ${first.x},${baselineY}`, 'Z'].join(' ')
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
