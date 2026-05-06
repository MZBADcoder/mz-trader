import { type MarketDataCapabilities } from '@/entities/market-capabilities'
import { type SnapshotRefreshState } from '@/features/snapshot-refresh'
import { useI18n } from '@/shared/i18n'
import { formatDateTime } from '@/shared/lib'

type Props = {
  capabilities: MarketDataCapabilities | null
  lastUpdatedAt: string | null
  state: SnapshotRefreshState
  onRefresh: () => void
}

export function MarketStatusBar({ capabilities, lastUpdatedAt, onRefresh, state }: Props) {
  const { locale, t } = useI18n()
  const modeLabel = capabilities?.is_realtime
    ? t('terminal.realtime')
    : `${t('terminal.delayed')} ${capabilities?.delay_minutes ?? '-'} ${t('terminal.minutes')}`

  return (
    <div className="market-status-bar">
      <div>
        <span className={`status-dot ${state}`} />
        <strong>{stateLabel(state, t)}</strong>
      </div>
      <div className="status-meta">
        <span>{modeLabel}</span>
        <span>
          {t('terminal.lastUpdated')}: {formatDateTime(lastUpdatedAt, locale, { timeZone: 'UTC' })}
        </span>
        <button className="icon-button" type="button" onClick={onRefresh}>
          {t('common.retry')}
        </button>
      </div>
    </div>
  )
}

function stateLabel(state: SnapshotRefreshState, t: (key: `terminal.${string}`) => string) {
  if (state === 'partial') {
    return t('terminal.snapshotsPartial')
  }
  if (state === 'degraded') {
    return t('terminal.snapshotsDegraded')
  }
  if (state === 'loading') {
    return t('terminal.snapshotsLoading')
  }
  return t('terminal.snapshotsFresh')
}
