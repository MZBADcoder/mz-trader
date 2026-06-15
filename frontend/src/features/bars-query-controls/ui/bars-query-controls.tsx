import {
  barAdjustmentOptions,
  barResolutions,
  barSessions,
  supportedBarAdjustments,
  type BarAdjustment,
  type BarAdjustmentOption,
  type BarResolution,
  type BarsControlsValue,
  type BarSession,
} from '../model/bars-controls'

import { useI18n } from '@/shared/i18n'

type Props = {
  value: BarsControlsValue
  error?: string | null
  onChange: (value: BarsControlsValue) => void
}

export function BarsQueryControls({ error, onChange, value }: Props) {
  const { t } = useI18n()

  return (
    <div className="bars-controls">
      <fieldset>
        <legend>{t('terminal.resolution')}</legend>
        <div className="chip-row">
          {barResolutions.map((resolution) => (
            <button
              className={value.resolution === resolution ? 'chip active' : 'chip'}
              key={resolution}
              type="button"
              onClick={() => onChange({ ...value, resolution })}
            >
              {resolutionLabel(resolution, t)}
            </button>
          ))}
        </div>
      </fieldset>

      <label className="select-control">
        <span>{t('terminal.session')}</span>
        <select
          value={value.session}
          onChange={(event) =>
            onChange({ ...value, session: event.target.value as BarSession })
          }
        >
          {barSessions.map((session) => (
            <option key={session} value={session}>
              {sessionLabel(session, t)}
            </option>
          ))}
        </select>
      </label>

      <fieldset>
        <legend>{t('terminal.adjustment')}</legend>
        <div className="chip-row">
          {barAdjustmentOptions.map((adjustment) => {
            const supported = isSupportedAdjustment(adjustment)
            return (
              <button
                className={value.adjustment === adjustment ? 'chip active' : 'chip'}
                disabled={!supported}
                key={adjustment}
                title={!supported ? t('terminal.rawUnsupported') : undefined}
                type="button"
                onClick={() => {
                  if (supported) {
                    onChange({ ...value, adjustment })
                  }
                }}
              >
                {adjustmentLabel(adjustment, t)}
              </button>
            )
          })}
        </div>
      </fieldset>

      {error ? <p className="inline-error">{error}</p> : null}
    </div>
  )
}

function sessionLabel(session: BarSession, t: (key: `terminal.${string}`) => string) {
  if (session === 'pre_market') {
    return t('terminal.preMarket')
  }
  if (session === 'after_hours') {
    return t('terminal.afterHours')
  }
  return t('terminal.regular')
}

function resolutionLabel(resolution: BarResolution, t: (key: `terminal.${string}`) => string) {
  return resolution === 'intraday' ? t('terminal.intraday') : resolution
}

function isSupportedAdjustment(adjustment: BarAdjustmentOption): adjustment is BarAdjustment {
  return supportedBarAdjustments.includes(adjustment as BarAdjustment)
}

function adjustmentLabel(adjustment: BarAdjustmentOption, t: (key: `terminal.${string}`) => string) {
  return adjustment === 'raw' ? t('terminal.raw') : t('terminal.adjusted')
}

export type { BarResolution, BarSession, BarsControlsValue }
