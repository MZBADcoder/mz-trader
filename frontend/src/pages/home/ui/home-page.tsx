import { CapabilityBand } from '@/widgets/capability-band'
import { HomepageHero } from '@/widgets/homepage-hero'

export function HomePage() {
  return (
    <main className="home-page">
      <HomepageHero />
      <CapabilityBand />
    </main>
  )
}
