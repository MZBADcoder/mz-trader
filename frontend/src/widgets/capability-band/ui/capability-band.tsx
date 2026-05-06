import { useI18n } from '@/shared/i18n'

const capabilityKeys = [
  ['observeTitle', 'observeText'],
  ['generateTitle', 'generateText'],
  ['backtestTitle', 'backtestText'],
  ['iterateTitle', 'iterateText'],
] as const

export function CapabilityBand() {
  const { t } = useI18n()

  return (
    <section className="capability-band" id="capabilities">
      <div className="section-inner">
        <p className="eyebrow">Research loop</p>
        <h2>{t('home.capabilityTitle')}</h2>
        <div className="capability-grid" id="workflow">
          {capabilityKeys.map(([titleKey, textKey], index) => (
            <article className="capability-item" key={titleKey}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              <h3>{t(`home.${titleKey}`)}</h3>
              <p>{t(`home.${textKey}`)}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
