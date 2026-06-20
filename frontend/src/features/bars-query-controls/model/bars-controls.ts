import { type SupportedBarAdjustment } from '@/entities/market-bars'

export const barResolutions = ['intraday', '1m', '5m', '15m', '30m', '60m', '1D', '1W', '1M'] as const
export const barSessions = ['regular'] as const
export const supportedBarAdjustments = ['split_adjusted'] as const satisfies readonly SupportedBarAdjustment[]
export const unavailableBarAdjustments = ['raw'] as const
export const barAdjustmentOptions = [...supportedBarAdjustments, ...unavailableBarAdjustments] as const

export type BarResolution = (typeof barResolutions)[number]
export type BarSession = (typeof barSessions)[number]
export type BarAdjustment = (typeof supportedBarAdjustments)[number]
export type BarAdjustmentOption = (typeof barAdjustmentOptions)[number]

export type BarsControlsValue = {
  resolution: BarResolution
  session: BarSession
  adjustment: BarAdjustment
}
