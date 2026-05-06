import { Link } from 'react-router-dom'

import { useAuth } from '@/features/auth'
import { useI18n } from '@/shared/i18n'

export function HomepageHero() {
  const { status } = useAuth()
  const { locale, setLocale, t } = useI18n()
  const terminalTarget = status === 'authenticated' ? '/terminal' : '/auth'

  return (
    <section className="home-hero">
      <div className="hero-background" aria-hidden="true" />
      <nav className="home-nav" aria-label="Primary">
        <Link className="brand-link" to="/">
          {t('common.brand')}
        </Link>
        <div className="nav-actions">
          <a href="#capabilities">{t('home.navCapabilities')}</a>
          <a href="#workflow">{t('home.navWorkflow')}</a>
          <label className="locale-control">
            <span>{t('common.language')}</span>
            <select value={locale} onChange={(event) => setLocale(event.target.value as typeof locale)}>
              <option value="zh-CN">{t('common.zh')}</option>
              <option value="en-US">{t('common.en')}</option>
            </select>
          </label>
          <Link className="ghost-button" to="/auth">
            {t('common.login')}
          </Link>
          <Link className="primary-button" to={terminalTarget}>
            {t('common.terminal')}
          </Link>
        </div>
      </nav>

      <div className="hero-content">
        <div className="hero-copy">
          <p className="eyebrow">{t('home.heroEyebrow')}</p>
          <h1>{t('home.heroTitle')}</h1>
          <p>{t('home.heroCopy')}</p>
          <div className="cta-row">
            <Link className="primary-button" to="/auth">
              {t('home.primaryCta')}
            </Link>
            <a className="ghost-button" href="#workflow">
              {t('home.secondaryCta')}
            </a>
          </div>
        </div>

        <div className="strategy-console" aria-label={t('home.visualTitle')}>
          <div className="console-header">
            <span>{t('home.visualTitle')}</span>
            <span>LIVE RESEARCH</span>
          </div>
          <div className="console-grid">
            <div>
              <strong>{t('home.visualDraft')}</strong>
              <p>breakout + volume expansion + session filter</p>
            </div>
            <div>
              <strong>{t('home.visualBacktest')}</strong>
              <p>generate.py --risk 0.8 --walk-forward</p>
            </div>
            <div>
              <strong>{t('home.visualValidation')}</strong>
              <p>win rate 54.2% / max drawdown 7.8%</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
